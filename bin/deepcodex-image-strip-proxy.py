#!/usr/bin/env python3
"""
DeepCodex 图生文中转 (image-strip / image-to-text shim)

为什么存在：DeepSeek V4 (flash/pro) 是纯文本模型，不支持图片输入。
对话里只要出现图片，整轮请求会被服务端拒绝（messages[N]: unknown variant `image_url`），
而且那张图留在历史里会让该会话之后每一轮都失败。

这个 shim 坐在 App 和 ccx 之间，处理发往 DeepSeek 的请求体里的图片：
- 【视觉开启时】把每张图片送到 LongCat-Flash-Omni 多模态模型转成文字描述，
  再把图片内容块替换成 `[图片内容：……]` 的文字块 —— DeepSeek 收到纯文本，
  既不崩、又能"间接看到"图。
- 【视觉关闭 / 识别失败时】回退到老行为：删掉图片块（必要时塞文字占位）。
响应流式原样透传，不做任何改动。

设计原则（稳定第一）：
- 视觉是"增强"，不是"依赖"：LongCat 超时/报错/没配 key 一律回退到剥图，绝不拖垮 DeepSeek。
- 按图片内容哈希缓存描述：对话历史每轮重发同一张图，只有第一次真正调 LongCat。
- ccx 一个字节不动；本进程挂掉只影响 DeepSeek 主链路，DeepCodex 不再保留 GPT/ChatGPT 回退路线。
- 非图片请求 / 非 JSON 请求 一律原样透传；响应流式透传，不缓冲。

视觉配置（均可选；没配 LONGCAT_API_KEY 时自动退化为纯剥图）：
- LONGCAT_API_KEY：从环境变量或 DEEPCODEX_HOME/secrets.env 读取。
- VISION_ENABLED=0 可强制关闭视觉。
- VISION_MODEL / VISION_TIMEOUT / VISION_MAX_CHARS 可调。

用法：
    deepcodex-image-strip-proxy.py             # 监听 127.0.0.1:3100，转发到 127.0.0.1:3000
    deepcodex-image-strip-proxy.py --selftest  # 离线单测剥图/替换逻辑，不联网
    deepcodex-image-strip-proxy.py --vision-test  # 联网测一张图，验证 LongCat 识图通路
"""
import hashlib
import http.client
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "3100"))
UPSTREAM_HOST = os.environ.get("UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("UPSTREAM_PORT", "3000"))
# ccx 的 stream_idle_timeout_ms 默认 300000，这里给足余量。
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT", "600"))

PLACEHOLDER_TEXT = "[图片已忽略：DeepCodex 当前只使用 DeepSeek，模型不支持原生图片输入]"

# 逐跳头部，转发时不应原样透传
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}

# ---------------------------------------------------------------------------
# 视觉（图生文）配置
# ---------------------------------------------------------------------------
SECRETS_ENV = os.path.join(
    os.path.expanduser(os.environ.get("DEEPCODEX_HOME", "~/.codex-deepseek")),
    "secrets.env",
)


def _load_longcat_key():
    """优先环境变量，其次从 secrets.env 读 LONGCAT_API_KEY。"""
    key = os.environ.get("LONGCAT_API_KEY")
    if key:
        return key.strip()
    try:
        with open(SECRETS_ENV, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("LONGCAT_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


LONGCAT_API_KEY = _load_longcat_key()
VISION_ENABLED = bool(LONGCAT_API_KEY) and os.environ.get("VISION_ENABLED", "1") != "0"
VISION_HOST = os.environ.get("VISION_HOST", "api.longcat.chat")
VISION_PATH = os.environ.get("VISION_PATH", "/openai/v1/chat/completions")
VISION_MODEL = os.environ.get("VISION_MODEL", "LongCat-Flash-Omni-2603")
VISION_TIMEOUT = float(os.environ.get("VISION_TIMEOUT", "30"))
VISION_MAX_CHARS = int(os.environ.get("VISION_MAX_CHARS", "4000"))
VISION_PROMPT = os.environ.get(
    "VISION_PROMPT",
    "请详细、客观地描述这张图片的全部内容：包括其中的文字（原样逐字列出）、"
    "图表、界面元素、物体、布局和关键细节，让看不到图的人也能完全理解这张图。",
)

# 描述缓存：sha256(图片数据) -> 描述文字。shim 是常驻进程，对话每轮重发同图只算一次。
_desc_cache = {}
_desc_cache_lock = threading.Lock()
_log_sink = None  # 由 Handler 注入，用于把视觉日志写到 stderr


def _vlog(msg):
    if _log_sink:
        _log_sink(msg)
    else:
        sys.stderr.write("[shim/vision] " + msg + "\n")


def _is_image_block(obj):
    if not isinstance(obj, dict):
        return False
    t = obj.get("type")
    if t == "input_image":
        return True
    # 防御：某些链路会用 chat-completions 风格的 image_url 内容块
    if t == "image_url" and ("image_url" in obj):
        return True
    return False


def _extract_image(block):
    """从图片块里取出 (kind, data)：
    kind="base64" 时 data 是裸 base64；kind="url" 时 data 是 http(s) 链接。
    取不到返回 (None, None)。"""
    val = block.get("image_url")
    if isinstance(val, dict):
        val = val.get("url")
    if not isinstance(val, str) or not val:
        return None, None
    if val.startswith("data:"):
        comma = val.find(",")
        if comma != -1:
            return "base64", val[comma + 1:]
        return None, None
    if val.startswith("http://") or val.startswith("https://"):
        return "url", val
    # 兜底：当作裸 base64
    return "base64", val


def describe_image(kind, data):
    """调用 LongCat Omni 把图片转成文字描述。失败/未启用返回 None（调用方回退到剥图）。"""
    if not VISION_ENABLED or not data:
        return None
    cache_key = hashlib.sha256((kind + "|" + data).encode("utf-8")).hexdigest()
    with _desc_cache_lock:
        if cache_key in _desc_cache:
            return _desc_cache[cache_key]

    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "input_image", "input_image": {"type": kind, "data": [data]}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
        "max_tokens": 1024,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + LONGCAT_API_KEY,
        "Content-Type": "application/json",
    }
    t0 = time.time()
    conn = http.client.HTTPSConnection(VISION_HOST, timeout=VISION_TIMEOUT)
    try:
        conn.request("POST", VISION_PATH, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            _vlog(f"LongCat HTTP {resp.status}: {raw[:160]!r} (回退剥图)")
            return None
        desc = json.loads(raw)["choices"][0]["message"]["content"]
        if not isinstance(desc, str) or not desc.strip():
            _vlog("LongCat 返回空描述 (回退剥图)")
            return None
        desc = desc.strip()
        if len(desc) > VISION_MAX_CHARS:
            desc = desc[:VISION_MAX_CHARS] + "…（描述已截断）"
        with _desc_cache_lock:
            _desc_cache[cache_key] = desc
        _vlog(f"图已识别 %.1fs, {len(desc)} 字" % (time.time() - t0))
        return desc
    except Exception as e:
        _vlog(f"LongCat 调用失败 ({type(e).__name__}: {e}) (回退剥图)")
        return None
    finally:
        conn.close()


def _image_block_to_text(block):
    """图片块 -> 文字块。识别成功返回 input_text 块；失败返回 None（调用方删除+占位）。"""
    kind, data = _extract_image(block)
    desc = describe_image(kind, data) if data else None
    if desc:
        return {"type": "input_text",
                "text": f"[图片内容（DeepSeek 不支持图片，以下由视觉模型识别）：\n{desc}\n]"}
    return None


def strip_images(node):
    """递归处理图片块：能识别就替换成文字描述，否则删除。
    返回 (新节点, 删除数, 识别数)。"""
    removed = 0
    described = 0
    if isinstance(node, list):
        new_list = []
        for item in node:
            if _is_image_block(item):
                text_block = _image_block_to_text(item)
                if text_block is not None:
                    new_list.append(text_block)
                    described += 1
                else:
                    removed += 1
                continue
            child, r, d = strip_images(item)
            removed += r
            described += d
            new_list.append(child)
        return new_list, removed, described
    if isinstance(node, dict):
        new_dict = {}
        for k, v in node.items():
            child, r, d = strip_images(v)
            removed += r
            described += d
            new_dict[k] = child
        # 如果这是一条消息且 content 被剥空了，塞一个文字占位，避免空内容引发新报错
        content = new_dict.get("content")
        if isinstance(content, list) and len(content) == 0 and "role" in new_dict:
            new_dict["content"] = [{"type": "input_text", "text": PLACEHOLDER_TEXT}]
        return new_dict, removed, described
    return node, removed, described


def transform_body(raw: bytes):
    """对 JSON 请求体处理图片。非 JSON 或无图则原样返回。
    返回 (新 body, 删除数, 识别数)。"""
    if not raw:
        return raw, 0, 0
    # 快速预筛，绝大多数请求没有图，直接放过，零解析开销
    if b"input_image" not in raw and b"image_url" not in raw:
        return raw, 0, 0
    try:
        obj = json.loads(raw)
    except Exception:
        return raw, 0, 0
    new_obj, removed, described = strip_images(obj)
    if removed == 0 and described == 0:
        return raw, 0, 0
    return json.dumps(new_obj, ensure_ascii=False).encode("utf-8"), removed, described


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "deepcodex-image-strip/2.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[shim] " + (fmt % args) + "\n")

    def log_request(self, *args, **kwargs):
        # 静默每条成功请求的访问行（KeepAlive 常驻会让 err.log 无限膨胀）。
        # 真正有意义的日志（剥图/识图、upstream/stream 错误）仍由显式 log_message / log_error 记录。
        pass

    def _proxy(self):
        # 读完整请求体
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length > 0 else b""

        new_body, removed, described = transform_body(body)
        if removed or described:
            self.log_message("images on %s: described=%d stripped=%d", self.path, described, removed)

        # 组装转发头部
        out_headers = {}
        for k, v in self.headers.items():
            if k.lower() in HOP_BY_HOP or k.lower() == "content-length":
                continue
            out_headers[k] = v
        out_headers["Content-Length"] = str(len(new_body))

        conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=UPSTREAM_TIMEOUT)
        try:
            conn.request(self.command, self.path, body=new_body, headers=out_headers)
            resp = conn.getresponse()
        except Exception as e:
            self.log_message("upstream error: %s", e)
            self.send_error(502, "upstream connection failed")
            conn.close()
            return

        # 回写状态行
        self.send_response(resp.status, resp.reason)
        # 透传响应头（去掉逐跳头和 content-length，自己用 chunked 流式回写）
        for k, v in resp.getheaders():
            lk = k.lower()
            if lk in HOP_BY_HOP or lk == "content-length":
                continue
            self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        # 流式透传响应体，不缓冲（SSE token 实时到达）
        try:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                self.wfile.write(b"%X\r\n" % len(chunk) + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except Exception as e:
            self.log_message("stream error: %s", e)
        finally:
            conn.close()

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_PATCH = _proxy


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # 客户端中途断连（取消流式回复）会在 recv/ send 抛 ConnectionResetError/
        # BrokenPipeError，这是正常现象，不该往 err.log 刷整段栈。其它异常保留栈。
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def run_selftest():
    """离线单测，不联网。验证两条路径：
    1) 视觉关闭/失败 -> 剥图 + 占位（向后兼容老行为）。
    2) 视觉成功（打桩）-> 图片块被替换成文字描述块。"""
    global VISION_ENABLED
    sample = {
        "model": "deepseek-v4-pro",
        "input": [
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "这是什么"},
                {"type": "input_image", "image_url": "data:image/png;base64," + "A" * 5000, "detail": "high"},
            ]},
            {"type": "message", "role": "user", "content": [
                {"type": "input_image", "image_url": "data:image/png;base64," + "B" * 3000},
            ]},
        ],
    }
    raw = json.dumps(sample, ensure_ascii=False).encode("utf-8")

    # --- 路径 1：视觉关闭 -> 剥图回退 ---
    saved = VISION_ENABLED
    VISION_ENABLED = False
    new_raw, removed, described = transform_body(raw)
    out = json.loads(new_raw)
    assert removed == 2 and described == 0, f"fallback: expected removed=2 described=0, got {removed}/{described}"
    c0 = out["input"][0]["content"]
    assert all(b.get("type") != "input_image" for b in c0), "image not stripped in msg0"
    assert any(b.get("type") == "input_text" for b in c0), "text lost in msg0"
    c1 = out["input"][1]["content"]
    assert len(c1) == 1 and c1[0]["type"] == "input_text", "emptied content not backfilled"
    assert b"input_image" not in new_raw, "input_image still present after strip"

    # --- 路径 2：视觉成功（打桩 describe_image） -> 替换成文字描述 ---
    import builtins  # noqa: F401  (保持 import 风格一致)
    global describe_image
    real_describe = describe_image
    describe_image = lambda kind, data: "一张测试图：写着 HELLO"  # noqa: E731
    VISION_ENABLED = True
    try:
        new_raw2, removed2, described2 = transform_body(raw)
    finally:
        describe_image = real_describe
        VISION_ENABLED = saved
    out2 = json.loads(new_raw2)
    assert removed2 == 0 and described2 == 2, f"vision: expected removed=0 described=2, got {removed2}/{described2}"
    assert b"input_image" not in new_raw2, "input_image should be replaced by text"
    joined = json.dumps(out2, ensure_ascii=False)
    assert "图片内容" in joined and "HELLO" in joined, "description not injected"

    # --- 无图请求必须原样返回 ---
    plain = json.dumps({"model": "x", "input": [{"type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "hi"}]}]}).encode()
    p2, r2, d2 = transform_body(plain)
    assert r2 == 0 and d2 == 0 and p2 == plain, "plain request must pass through unchanged"

    print("selftest OK: 剥图回退 / 图生文替换 / 纯文本透传 三条路径均正确")


def run_vision_test():
    """联网验证 LongCat 识图通路。优先用 PIL 生成带文字的图，验证能否读出文字。"""
    if not LONGCAT_API_KEY:
        print("[vision-test] 未配置 LONGCAT_API_KEY（env 或 secrets.env），视觉处于关闭态。")
        return
    import base64
    token = "VISIONTEST-" + str(int(time.time()) % 100000)
    b64 = None
    try:
        import io
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (380, 120), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([8, 8, 372, 112], outline="black", width=3)
        d.text((30, 50), token, fill="black")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        print(f"[vision-test] 已生成测试图，内嵌文字: {token}")
    except Exception as e:
        print(f"[vision-test] 无 PIL（{e}），跳过文字校验，仅验证通路。")
    if b64 is None:
        # 1x1 像素红点 PNG，仅验证调用链通不通
        b64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYGAA"
               "AAAEAAH2FzhVAAAAAElFTkSuQmCC")
        token = None
    desc = describe_image("base64", b64)
    if desc is None:
        print("[vision-test] ❌ 识别失败/超时（已安全回退到剥图模式，不影响 DeepSeek）。")
        return
    print("[vision-test] ✅ 识别成功，模型描述：")
    print("  " + desc.replace("\n", "\n  "))
    if token:
        print("  >>> 读到内嵌文字!" if token in desc else "  >>> ⚠️ 未读到内嵌文字（图小或被压缩）")


def main():
    if "--selftest" in sys.argv:
        run_selftest()
        return
    if "--vision-test" in sys.argv:
        run_vision_test()
        return
    server = QuietThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    vstate = f"视觉已开启 ({VISION_MODEL})" if VISION_ENABLED else "视觉关闭（纯剥图）"
    sys.stderr.write(
        f"[shim] listening {LISTEN_HOST}:{LISTEN_PORT} -> {UPSTREAM_HOST}:{UPSTREAM_PORT} | {vstate}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
