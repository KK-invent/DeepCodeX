#!/usr/bin/env python3
"""
deepcodex-deepseek-bridge.py
Replaces the private ccx binary with a pure Python translation layer.

Translates OpenAI Responses API (POST /v1/responses) to DeepSeek
Chat Completions API (POST /v1/chat/completions) and back.

Listens on 127.0.0.1:3000 (env BRIDGE_LISTEN_HOST / BRIDGE_LISTEN_PORT).
Reads DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, CCX_PROXY_ACCESS_KEY
from ~/.codex-deepseek/secrets.env (or env vars).

Usage:
  python3 bin/deepcodex-deepseek-bridge.py
  python3 bin/deepcodex-deepseek-bridge.py --selftest
  python3 bin/deepcodex-deepseek-bridge.py --help
"""
import argparse
import json
import os
import random
import re
import socketserver
import string
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Constants ──────────────────────────────────────────────────────────────

DEEPCODEX_HOME = os.environ.get(
    "DEEPCODEX_HOME",
    os.path.expanduser("~/.codex-deepseek"),
)

SECRETS_FILE = os.path.join(DEEPCODEX_HOME, "secrets.env")

DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 3000

# Default model mapping — overridable via env
DEFAULT_MODEL_FLASH = "deepseek-chat"
DEFAULT_MODEL_PRO = "deepseek-reasoner"

# DeepSeek uses "deepseek" as the chat model id
MODEL_MAP = {
    "deepseek-v4-flash": os.environ.get("DEEPSEEK_MODEL_FLASH", DEFAULT_MODEL_FLASH),
    "deepseek-v4-pro": os.environ.get("DEEPSEEK_MODEL_PRO", DEFAULT_MODEL_PRO),
}

# ── Helpers ────────────────────────────────────────────────────────────────

def _vlog(msg):
    print(f"[bridge] {msg}", file=sys.stderr, flush=True)


def load_secrets():
    """Load secrets from secrets.env, preferring env vars over file values."""
    secrets = {}
    env_path = SECRETS_FILE
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    secrets[k.strip()] = v.strip()

    # env vars override file
    for key in ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "CCX_PROXY_ACCESS_KEY"):
        ev = os.environ.get(key)
        if ev:
            secrets[key] = ev

    return secrets


def random_id(prefix="", length=24):
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return f"{prefix}{suffix}"


def now_unix():
    return int(time.time())


# ── Request Translation: Responses → Chat Completions ─────────────────────

def translate_request(responses_body):
    """
    Translate a Responses API request body to a Chat Completions request body.
    Returns (chat_body, response_model_name).
    """
    chat = {}

    # Model mapping
    req_model = responses_body.get("model", "deepseek-v4-flash")
    upstream_model = MODEL_MAP.get(req_model, req_model)
    chat["model"] = upstream_model

    # Instructions → system message
    messages = []
    instructions = responses_body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    # Input items → messages
    input_items = responses_body.get("input", [])
    for item in input_items:
        if isinstance(item, dict) and "role" in item:
            # Simple role-based message
            role = item.get("role", "user")
            content_blocks = item.get("content", [])
            text = _extract_text(content_blocks)
            if text is not None:
                messages.append({"role": role, "content": text})
        elif isinstance(item, dict) and "type" in item:
            t = item["type"]
            if t == "function_call":
                # Previous function call in history
                msg = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": item.get("call_id", item.get("id", "")),
                        "type": "function",
                        "function": {
                            "name": item.get("name", ""),
                            "arguments": item.get("arguments", "{}"),
                        },
                    }],
                }
                messages.append(msg)
            elif t == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": item.get("output", ""),
                })
            elif t == "reasoning":
                # DeepSeek doesn't consume reasoning history — skip
                pass
            elif t == "message":
                role = item.get("role", "assistant")
                text = _extract_text(item.get("content", []))
                if text is not None:
                    messages.append({"role": role, "content": text})

    chat["messages"] = messages

    # Tools
    tools = responses_body.get("tools")
    if tools:
        chat["tools"] = [_translate_tool(t) for t in tools]

    # tool_choice
    tc = responses_body.get("tool_choice")
    if tc is not None:
        chat["tool_choice"] = tc

    # parallel_tool_calls
    ptc = responses_body.get("parallel_tool_calls")
    if ptc is not None:
        chat["parallel_tool_calls"] = ptc

    # Other params
    for k in ("max_output_tokens", "temperature", "top_p", "stop"):
        v = responses_body.get(k)
        if v is not None:
            chat_key = "max_tokens" if k == "max_output_tokens" else k
            chat[chat_key] = v

    # Streaming
    chat["stream"] = responses_body.get("stream", True)

    # Always ask for usage in streaming
    if chat.get("stream"):
        chat["stream_options"] = {"include_usage": True}

    return chat, req_model


def _extract_text(content_blocks):
    """Join text from content blocks (input_text/output_text/text)."""
    if not content_blocks:
        return ""
    texts = []
    for b in content_blocks:
        if isinstance(b, str):
            texts.append(b)
        elif isinstance(b, dict):
            btype = b.get("type", "")
            if btype in ("input_text", "output_text", "text"):
                texts.append(b.get("text", ""))
    return "".join(texts) if texts else None


def _translate_tool(t):
    """Translate a Responses-API tool to Chat Completions tool format."""
    out = {"type": t.get("type", "function")}
    f = t.get("function", {})
    if out["type"] == "function":
        out["function"] = {
            "name": t.get("name", f.get("name", "")),
            "description": t.get("description", f.get("description", "")),
            "parameters": t.get("parameters", f.get("parameters", {})),
        }
    return out


# ── Response Translation (Non-streaming) ───────────────────────────────────

def build_nonstreaming_response(chat_resp_body, req_model):
    """
    Build a Responses API response object from a Chat Completions response body.
    """
    choice = chat_resp_body.get("choices", [{}])[0]
    msg = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")

    output = []
    # Reasoning content (from DeepSeek reasoner)
    reasoning_content = msg.get("reasoning_content", "")
    if reasoning_content:
        output.append({
            "type": "reasoning",
            "status": "completed",
            "summary": [{"text": reasoning_content, "type": "summary_text"}],
        })

    # Tool calls
    tool_calls = msg.get("tool_calls", [])
    for tc in tool_calls:
        output.append({
            "type": "function_call",
            "id": f"fc_call_00_{tc.get('id', random_id())}",
            "call_id": tc.get("id", ""),
            "name": tc.get("function", {}).get("name", ""),
            "arguments": tc.get("function", {}).get("arguments", "{}"),
            "status": "completed",
        })

    # Text content
    content = msg.get("content", "")
    if content:
        output.append({
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": content}],
        })

    usage = chat_resp_body.get("usage", {})
    status = "completed" if finish_reason == "stop" else "in_progress"

    return {
        "id": f"resp_{random_id('', 16)}",
        "object": "response",
        "created_at": now_unix(),
        "status": status if not _is_error_status(finish_reason) else "failed",
        "error": None if finish_reason == "stop" else _error_from_finish(finish_reason),
        "incomplete_details": None,
        "model": req_model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


def _is_error_status(finish_reason):
    return finish_reason in ("error", "length", "content_filter")


def _error_from_finish(finish_reason):
    if finish_reason == "length":
        return {"type": "max_tokens", "message": "Maximum output tokens reached"}
    if finish_reason == "content_filter":
        return {"type": "content_filter", "message": "Content filtered by model"}
    return {"type": "error", "message": f"Unknown finish_reason: {finish_reason}"}


# ── Response Translation (Streaming SSE) ───────────────────────────────────

def build_streaming_events(chat_chunk, state):
    """
    Given a Chat Completions chunk and accumulated state, yield
    (event_type, event_data_dict) tuples for the Responses SSE stream.

    state is a dict with:
      - seq: int (incremented per event)
      - response_id: str
      - created_at: int
      - req_model: str
      - instructions: str
      - tools: list
      - tool_choice: str
      - reasoning_item_id: str or None
      - msg_item_id: str or None
      - content_index: int
      - output_index: int
      - summary_index: int
      - text_buf: str
      - tool_calls: list
      - reasoning_text: str
      - function_call_received: bool
      - reasoning_received: bool
      - msg_received: bool
    Returns (list of events) or None if no events to emit.
    """
    events = []

    def _emit(etype, data):
        state["seq"] += 1
        data["sequence_number"] = state["seq"]
        events.append((etype, data))

    choices = chat_chunk.get("choices", [])
    if not choices:
        # Might be a usage-only chunk
        usage = chat_chunk.get("usage")
        if usage:
            _finalize(state, usage, events)
        return events

    delta = choices[0].get("delta", {})
    finish_reason = choices[0].get("finish_reason")

    # Handle reasoning_content (DeepSeek reasoner)
    reasoning_content = delta.get("reasoning_content", "")
    content = delta.get("content", "")
    tool_calls_delta = delta.get("tool_calls", [])

    # First chunk with any content — emit created + in_progress
    if state["seq"] == 0:
        _emit("response.created", {
            "type": "response.created",
            "response": {
                "id": state["response_id"],
                "object": "response",
                "created_at": state["created_at"],
                "status": "in_progress",
                "background": False,
                "error": None,
                "instructions": state.get("instructions", ""),
            },
        })
        _emit("response.in_progress", {
            "type": "response.in_progress",
            "response": {
                "id": state["response_id"],
                "object": "response",
                "created_at": state["created_at"],
                "status": "in_progress",
            },
        })
        # Emit tools if present
        tools = state.get("tools", [])
        if tools:
            # tools field goes into response.completed, not as separate events
            pass

    # Reasoning content delta
    if reasoning_content:
        if not state.get("reasoning_item_id"):
            state["reasoning_item_id"] = f"rs_{state['response_id']}_0"
            state["reasoning_received"] = True
            state["output_index"] += 1
            state["reasoning_output_index"] = state["output_index"]
            rid = state["reasoning_item_id"]
            _emit("response.output_item.added", {
                "type": "response.output_item.added",
                "output_index": state["reasoning_output_index"],
                "item": {
                    "id": rid,
                    "type": "reasoning",
                    "status": "in_progress",
                    "summary": [],
                },
            })
            state["summary_index"] = 0
            _emit("response.reasoning_summary_part.added", {
                "type": "response.reasoning_summary_part.added",
                "item_id": rid,
                "output_index": state["reasoning_output_index"],
                "summary_index": state["summary_index"],
                "part": {"type": "summary_text", "text": ""},
            })
        state["reasoning_text"] += reasoning_content
        _emit("response.reasoning_summary_text.delta", {
            "type": "response.reasoning_summary_text.delta",
            "item_id": state["reasoning_item_id"],
            "output_index": state["reasoning_output_index"],
            "summary_index": state["summary_index"],
            "text": reasoning_content,
        })

    # Tool calls delta
    if tool_calls_delta:
        for tc in tool_calls_delta:
            tc_index = tc.get("index", 0)
            tc_id = tc.get("id", "")
            tc_func = tc.get("function", {})

            # Check if this is a new tool call
            existing = None
            for etc in state.get("tool_calls", []):
                if etc.get("index") == tc_index:
                    existing = etc
                    break

            if existing is None:
                # New tool call
                state["function_call_received"] = True
                state["output_index"] += 1
                item_id = f"fc_call_{tc_index}_{random_id('', 16)}"
                name = tc_func.get("name", "")
                call_id_param = tc_id or f"call_{tc_index}_{random_id('', 8)}"
                tc_entry = {
                    "index": tc_index,
                    "output_index": state["output_index"],
                    "item_id": item_id,
                    "call_id": call_id_param,
                    "name": name,
                    "arguments_buf": tc_func.get("arguments", ""),
                    "name_received": bool(name),
                }
                state["tool_calls"].append(tc_entry)
                existing = tc_entry

                # Emit output_item.added for function_call
                _emit("response.output_item.added", {
                    "type": "response.output_item.added",
                    "output_index": existing["output_index"],
                    "item": {
                        "id": existing["item_id"],
                        "type": "function_call",
                        "status": "in_progress",
                        "arguments": "",
                        "call_id": existing["call_id"],
                        "name": existing["name"],
                    },
                })
                # Emit first arguments delta
                args_delta = tc_func.get("arguments", "")
                if args_delta:
                    _emit("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "item_id": existing["item_id"],
                        "output_index": existing["output_index"],
                        "delta": args_delta,
                    })
            else:
                # Existing tool call — accumulate arguments
                args_delta = tc_func.get("arguments", "")
                if args_delta:
                    existing["arguments_buf"] += args_delta
                    _emit("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "item_id": existing["item_id"],
                        "output_index": existing["output_index"],
                        "delta": args_delta,
                    })
                if tc_func.get("name") and not existing["name_received"]:
                    existing["name"] = tc_func["name"]
                    existing["name_received"] = True

    # Content delta (text)
    if content:
        if not state.get("msg_item_id"):
            state["msg_item_id"] = f"msg_{state['response_id']}_{len(state.get('tool_calls', [])) + 1}"
            state["msg_received"] = True
            state["output_index"] += 1
            state["msg_output_index"] = state["output_index"]
            state["content_index"] = 0
            mid = state["msg_item_id"]
            _emit("response.output_item.added", {
                "type": "response.output_item.added",
                "output_index": state["msg_output_index"],
                "item": {
                    "id": mid,
                    "type": "message",
                    "status": "in_progress",
                    "content": [],
                    "role": "assistant",
                },
            })
            _emit("response.content_part.added", {
                "type": "response.content_part.added",
                "item_id": mid,
                "output_index": state["msg_output_index"],
                "content_index": state["content_index"],
                "part": {
                    "type": "output_text",
                    "annotations": [],
                    "logprobs": [],
                    "text": "",
                },
            })
        state["text_buf"] += content
        _emit("response.output_text.delta", {
            "type": "response.output_text.delta",
            "item_id": state["msg_item_id"],
            "output_index": state["msg_output_index"],
            "content_index": state["content_index"],
            "delta": content,
            "logprobs": [],
        })

    # Finish
    if finish_reason:
        _finalize(state, chat_chunk.get("usage"), events)
        # Also emit the events we've accumulated (they need to be returned)
        return events

    return events


def _finalize(state, usage, events):
    """Emit done/completed events for all open items."""
    def _emit(etype, data):
        state["seq"] += 1
        data["sequence_number"] = state["seq"]
        events.append((etype, data))

    # Close reasoning item
    if state.get("reasoning_item_id"):
        rid = state["reasoning_item_id"]
        out_idx = state.get("reasoning_output_index", 0)
        _emit("response.reasoning_summary_text.done", {
            "type": "response.reasoning_summary_text.done",
            "item_id": rid,
            "output_index": out_idx,
            "summary_index": state["summary_index"],
            "text": state.get("reasoning_text", ""),
        })
        _emit("response.reasoning_summary_part.done", {
            "type": "response.reasoning_summary_part.done",
            "item_id": rid,
            "output_index": out_idx,
            "summary_index": state["summary_index"],
            "part": {
                "type": "summary_text",
                "text": state.get("reasoning_text", ""),
            },
        })
        _emit("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": out_idx,
            "item": {
                "id": rid,
                "type": "reasoning",
                "status": "completed",
                "summary": [{
                    "text": state.get("reasoning_text", ""),
                    "type": "summary_text",
                }],
            },
        })

    # Close message item
    mid = state.get("msg_item_id")
    if mid:
        out_idx = state.get("msg_output_index", state["output_index"])
        _emit("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": mid,
            "output_index": out_idx,
            "content_index": state["content_index"],
            "text": state.get("text_buf", ""),
            "logprobs": [],
        })
        _emit("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": mid,
            "output_index": out_idx,
            "content_index": state["content_index"],
            "part": {
                "type": "output_text",
                "annotations": [],
                "logprobs": [],
                "text": state.get("text_buf", ""),
            },
        })
        _emit("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": out_idx,
            "item": {
                "id": mid,
                "type": "message",
                "status": "completed",
                "content": [{
                    "type": "output_text",
                    "annotations": [],
                    "logprobs": [],
                    "text": state.get("text_buf", ""),
                }],
                "role": "assistant",
            },
        })

    # Close tool call items
    for tc in state.get("tool_calls", []):
        _emit("response.function_call_arguments.done", {
            "type": "response.function_call_arguments.done",
            "item_id": tc["item_id"],
            "output_index": tc["output_index"],
            "arguments": tc["arguments_buf"],
        })
        _emit("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": tc["output_index"],
            "item": {
                "id": tc["item_id"],
                "type": "function_call",
                "status": "completed",
                "arguments": tc["arguments_buf"],
                "call_id": tc["call_id"],
                "name": tc["name"],
            },
        })

    # Build output array for response.completed
    output_items = []
    if state.get("reasoning_item_id"):
        output_items.append((state.get("reasoning_output_index", 0), {
            "id": state["reasoning_item_id"],
            "type": "reasoning",
            "status": "completed",
            "summary": [{"text": state.get("reasoning_text", ""), "type": "summary_text"}],
        }))
    for tc in state.get("tool_calls", []):
        output_items.append((tc["output_index"], {
            "id": tc["item_id"],
            "type": "function_call",
            "status": "completed",
            "arguments": tc["arguments_buf"],
            "call_id": tc["call_id"],
            "name": tc["name"],
        }))
    if mid:
        output_items.append((state.get("msg_output_index", state["output_index"]), {
            "id": mid,
            "type": "message",
            "status": "completed",
            "content": [{
                "type": "output_text",
                "annotations": [],
                "logprobs": [],
                "text": state.get("text_buf", ""),
            }],
            "role": "assistant",
        }))

    usage_data = usage or {}
    _emit("response.completed", {
        "type": "response.completed",
        "response": {
            "id": state["response_id"],
            "object": "response",
            "created_at": state["created_at"],
            "status": "completed",
            "background": False,
            "error": None,
            "instructions": state.get("instructions", ""),
            "model": state.get("req_model", "deepseek-v4-flash"),
            "tool_choice": state.get("tool_choice"),
            "tools": state.get("tools", []),
            "output": [item for _, item in sorted(output_items, key=lambda pair: pair[0])],
            "usage": {
                "input_tokens": usage_data.get("prompt_tokens", 0),
                "output_tokens": usage_data.get("completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0),
                "output_tokens_details": {
                    "reasoning_tokens": usage_data.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
                } if usage_data.get("completion_tokens_details") else {},
            },
        },
    })


# ── HTTP Handler ──────────────────────────────────────────────────────────

class BridgeHandler(BaseHTTPRequestHandler):
    secrets = {}
    quiet = False

    def _vlog(self, msg):
        if not self.quiet:
            _vlog(msg)

    def _get_secret(self, key):
        return self.secrets.get(key) or os.environ.get(key)

    def _json_error(self, code, msg):
        body = json.dumps({"error": {"message": msg, "type": "bridge_error"}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self):
        self._json_error(401, "Invalid or missing API key")

    def _check_auth(self):
        auth = self.headers.get("Authorization", "")
        expected = self._get_secret("CCX_PROXY_ACCESS_KEY")
        if not expected:
            return True  # no auth configured = allow
        if auth.startswith("Bearer ") and auth[len("Bearer "):] == expected:
            return True
        self._unauthorized()
        return False

    def do_POST(self):
        if self.path == "/v1/responses":
            self._handle_responses()
        elif self.path.startswith("/v1/models"):
            self._handle_models()
        elif self.path == "/healthz":
            self._handle_health()
            return
        else:
            self._json_error(404, f"Not found: {self.path}")

    def _handle_models(self):
        body = json.dumps({
            "data": [
                {"id": "deepseek-v4-flash", "object": "model", "created": now_unix(), "owned_by": "deepseek"},
                {"id": "deepseek-v4-pro", "object": "model", "created": now_unix(), "owned_by": "deepseek"},
            ]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_health(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def _handle_responses(self):
        if not self._check_auth():
            return

        secrets = self.secrets
        deepseek_key = secrets.get("DEEPSEEK_API_KEY")
        deepseek_url = secrets.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

        if not deepseek_key:
            self._json_error(503, json.dumps({
                "message": "DeepSeek API key not configured. "
                           "Open DeepCodeX → Menu → 'Configure DeepSeek...' "
                           "or run: ~/.codex-deepseek/bin/deepcodex-configure-deepseek.py",
                "config_key": "DEEPSEEK_API_KEY",
                "config_help": "Edit ~/.codex-deepseek/secrets.env and set DEEPSEEK_API_KEY=<your key>",
            }))
            return

        length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(length)

        try:
            req_body = json.loads(body_raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json_error(400, f"Invalid JSON body: {e}")
            return

        is_streaming = req_body.get("stream", True)

        try:
            chat_body, req_model = translate_request(req_body)
        except Exception as e:
            self._vlog(f"translate_request error: {e}")
            self._json_error(500, f"Translation error: {e}")
            return

        # Forward to DeepSeek
        chat_url = f"{deepseek_url.rstrip('/')}/v1/chat/completions"
        chat_headers = {
            "Authorization": f"Bearer {deepseek_key}",
            "Content-Type": "application/json",
        }
        if is_streaming:
            chat_headers["Accept"] = "text/event-stream"

        _vlog(f"Forwarding: model={chat_body.get('model')} stream={is_streaming} "
              f"messages={len(chat_body.get('messages', []))} tools={len(chat_body.get('tools', []))}")

        ds_req = Request(chat_url, data=json.dumps(chat_body).encode(), headers=chat_headers, method="POST")

        try:
            ds_resp = urlopen(ds_req, timeout=180)
        except URLError as e:
            status = getattr(e, "code", 502)
            reason = str(e.reason) if hasattr(e, "reason") else str(e)
            self._vlog(f"DeepSeek upstream error: {status} {reason}")
            try:
                err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            except Exception:
                err_body = ""
            err_detail = err_body[:500] if err_body else reason
            self._send_deepseek_error(status, err_detail, req_model)
            return
        except Exception as e:
            self._vlog(f"DeepSeek connection error: {e}")
            self._send_deepseek_error(502, str(e), req_model)
            return

        if is_streaming:
            self._handle_streaming_response(ds_resp, req_body, req_model)
        else:
            self._handle_nonstreaming_response(ds_resp, req_model)

    def _send_deepseek_error(self, status, detail, req_model):
        """Return a structured error response."""
        resp = {
            "id": f"resp_{random_id('', 16)}",
            "object": "response",
            "created_at": now_unix(),
            "status": "failed",
            "error": {
                "type": "upstream_error",
                "message": f"DeepSeek API error: {detail}"[:500],
            },
            "incomplete_details": None,
            "model": req_model,
            "output": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
        body = json.dumps(resp).encode()
        try:
            self.send_response(status if status < 600 else 502)
        except Exception:
            self.send_response(502)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_nonstreaming_response(self, ds_resp, req_model):
        try:
            data = json.loads(ds_resp.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json_error(502, f"Invalid DeepSeek response: {e}")
            return

        try:
            resp = build_nonstreaming_response(data, req_model)
        except Exception as e:
            self._vlog(f"build_nonstreaming_response error: {e}")
            self._send_deepseek_error(502, f"Response build error: {e}", req_model)
            return

        body = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_streaming_response(self, ds_resp, req_body, req_model):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        state = {
            "seq": 0,
            "response_id": f"resp_{random_id('', 16)}",
            "created_at": now_unix(),
            "req_model": req_model,
            "instructions": req_body.get("instructions", ""),
            "tools": req_body.get("tools", []),
            "tool_choice": req_body.get("tool_choice"),
            "reasoning_item_id": None,
            "msg_item_id": None,
            "content_index": 0,
            "output_index": -1,
            "summary_index": 0,
            "text_buf": "",
            "tool_calls": [],
            "reasoning_text": "",
            "function_call_received": False,
            "reasoning_received": False,
            "msg_received": False,
        }

        buf = ""
        for raw_chunk in _iter_sse(ds_resp):
            if raw_chunk.startswith("data: "):
                chunk_data = raw_chunk[6:]
                if chunk_data.strip() == "[DONE]":
                    break
                try:
                    chat_chunk = json.loads(chunk_data)
                except json.JSONDecodeError:
                    self._vlog(f"Failed to parse chunk: {chunk_data[:100]}")
                    continue

                try:
                    events = build_streaming_events(chat_chunk, state)
                except Exception as e:
                    self._vlog(f"build_streaming_events error: {e}")
                    continue

                for etype, edata in events:
                    line = f"event: {etype}\ndata: {json.dumps(edata, ensure_ascii=False)}\n\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()

        self.wfile.flush()

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            self._handle_models()
        elif self.path == "/healthz":
            self._handle_health()
        else:
            self._json_error(404, f"Not found: {self.path}")

    def log_message(self, fmt, *args):
        pass


def _iter_sse(resp):
    """Iterate SSE event data lines from a response."""
    buf = ""
    while True:
        chunk = resp.read(8192)
        if not chunk:
            break
        buf += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buf:
            raw_event, buf = buf.split("\n\n", 1)
            for line in raw_event.split("\n"):
                if line.startswith("data: "):
                    yield line
                    break
    # remaining
    if buf.strip():
        for line in buf.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                yield line


# ── Self Test ──────────────────────────────────────────────────────────────

def run_selftest():
    """Offline self-test: verify request translation and event building."""
    _vlog("Running self-test...")
    errors = 0

    # Test 1: Basic request translation (non-streaming)
    req = {
        "model": "deepseek-v4-flash",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Hello"}]}],
        "instructions": "Be helpful.",
        "stream": False,
    }
    chat_body, req_model = translate_request(req)
    assert chat_body["model"] == "deepseek-chat", f"Expected deepseek-chat, got {chat_body['model']}"
    assert chat_body["messages"][0]["role"] == "system"
    assert chat_body["messages"][0]["content"] == "Be helpful."
    assert chat_body["messages"][1]["role"] == "user"
    assert chat_body["messages"][1]["content"] == "Hello"
    assert chat_body["stream"] is False
    _vlog("  [PASS] request translation (non-streaming)")

    # Test 2: Request translation with tools
    req2 = {
        "model": "deepseek-v4-flash",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "What time?"}]}],
        "tools": [{"type": "function", "name": "get_time", "description": "Get time", "parameters": {"type": "object", "properties": {}}}],
        "stream": True,
    }
    chat2, _ = translate_request(req2)
    assert len(chat2["tools"]) == 1
    assert chat2["tools"][0]["function"]["name"] == "get_time"
    assert chat2["stream"] is True
    assert chat2.get("stream_options", {}).get("include_usage") is True
    _vlog("  [PASS] request translation (with tools)")

    # Test 3: Request translation with function_call history
    req3 = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Read file"}]},
            {"type": "function_call", "call_id": "call_1", "name": "read_file", "arguments": '{"path":"test.txt"}'},
            {"type": "function_call_output", "call_id": "call_1", "output": "file content"},
        ],
        "stream": False,
    }
    chat3, model3 = translate_request(req3)
    assert model3 == "deepseek-v4-pro"
    assert chat3["model"] == "deepseek-reasoner"
    assert len(chat3["messages"]) == 3
    assert chat3["messages"][1]["tool_calls"][0]["function"]["name"] == "read_file"
    assert chat3["messages"][2]["role"] == "tool"
    _vlog("  [PASS] request translation (with tool history)")

    # Test 4: Non-streaming response building
    ds_resp_body = {
        "id": "chatcmpl-xxx",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Hello! How can I help?",
                "tool_calls": [],
            },
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    resp = build_nonstreaming_response(ds_resp_body, "deepseek-v4-flash")
    assert resp["model"] == "deepseek-v4-flash", f"Expected deepseek-v4-flash, got {resp['model']}"
    assert resp["status"] == "completed"
    assert resp["output"][0]["type"] == "message"
    assert resp["output"][0]["content"][0]["text"] == "Hello! How can I help?"
    assert resp["usage"]["input_tokens"] == 10
    _vlog("  [PASS] non-streaming response building")

    # Test 5: Non-streaming response with tool calls
    ds_resp2 = {
        "id": "chatcmpl-yyy",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_abc123",
                    "type": "function",
                    "function": {"name": "get_time", "arguments": "{}"},
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23},
    }
    resp2 = build_nonstreaming_response(ds_resp2, "deepseek-v4-flash")
    assert resp2["output"][0]["type"] == "function_call"
    assert resp2["output"][0]["name"] == "get_time"
    _vlog("  [PASS] non-streaming response (tool calls)")

    # Test 6: Streaming event building (simulated chunks)
    state = {
        "seq": 0, "response_id": f"resp_{random_id('', 16)}",
        "created_at": now_unix(), "req_model": "deepseek-v4-flash",
        "instructions": "", "tools": [], "tool_choice": None,
        "reasoning_item_id": None, "msg_item_id": None,
        "content_index": 0, "output_index": -1, "summary_index": 0,
        "text_buf": "", "tool_calls": [], "reasoning_text": "",
        "function_call_received": False, "reasoning_received": False,
        "msg_received": False,
    }

    # Simulate first chunk with reasoning
    chunk1 = {"choices": [{"delta": {"role": "assistant", "reasoning_content": "I think "}, "index": 0}]}
    evts1 = build_streaming_events(chunk1, state)
    assert len(evts1) > 0
    assert evts1[0][0] == "response.created"
    chunk1b = {"choices": [{"delta": {"content": "answer"}, "index": 0, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}
    evts1b = build_streaming_events(chunk1b, state)
    reasoning_done = [e for e in evts1b if e[0] == "response.reasoning_summary_text.done"][0][1]
    message_done = [e for e in evts1b if e[0] == "response.output_text.done"][0][1]
    assert reasoning_done["output_index"] == 0, reasoning_done
    assert message_done["output_index"] == 1, message_done
    _vlog(f"  [PASS] streaming event indexes (reasoning + text, {len(evts1) + len(evts1b)} events)")

    # Simulate text completion
    state2 = {
        "seq": 0, "response_id": f"resp_{random_id('', 16)}",
        "created_at": now_unix(), "req_model": "deepseek-v4-flash",
        "instructions": "", "tools": [], "tool_choice": None,
        "reasoning_item_id": None, "msg_item_id": None,
        "content_index": 0, "output_index": -1, "summary_index": 0,
        "text_buf": "", "tool_calls": [], "reasoning_text": "",
        "function_call_received": False, "reasoning_received": False,
        "msg_received": False,
    }
    chunk_a = {"choices": [{"delta": {"content": "Hello"}, "index": 0}]}
    evts_a = build_streaming_events(chunk_a, state2)
    assert len(evts_a) > 0

    chunk_b = {"choices": [{"delta": {"content": " world"}, "index": 0, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}}
    evts_b = build_streaming_events(chunk_b, state2)
    # Should have output_text.delta for " world" + done events + completed
    done_types = [e[0] for e in evts_b]
    assert "response.output_text.done" in done_types, f"Missing output_text.done in {done_types}"
    assert "response.completed" in done_types, f"Missing response.completed in {done_types}"
    _vlog(f"  [PASS] streaming text completion ({len(evts_b)} final events)")

    # Test 7: Non-streaming smoke test compliance (echo model name)
    ds_smoke = {
        "id": "chatcmpl-zzz",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
    }
    resp_smoke = build_nonstreaming_response(ds_smoke, "deepseek-v4-flash")
    assert resp_smoke["model"] == "deepseek-v4-flash"
    assert resp_smoke["status"] == "completed"
    _vlog("  [PASS] smoke test compliance (model echo + status)")

    _vlog("  All 8 self-tests passed!")
    return 0 if errors == 0 else 1


# ── Server ─────────────────────────────────────────────────────────────────

class ThreadingBridgeServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    p = argparse.ArgumentParser(description="DeepCodeX DeepSeek Bridge")
    p.add_argument("--listen-host", default=DEFAULT_LISTEN_HOST)
    p.add_argument("--listen-port", type=int, default=DEFAULT_LISTEN_PORT)
    p.add_argument("--secrets-file", default=SECRETS_FILE)
    p.add_argument("--selftest", action="store_true", help="Run offline self-test and exit")
    p.add_argument("--quiet", action="store_true", help="Suppress runtime logging")
    args = p.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    # Load secrets
    secrets = load_secrets()
    BridgeHandler.secrets = secrets
    BridgeHandler.quiet = args.quiet

    host = os.environ.get("BRIDGE_LISTEN_HOST", args.listen_host)
    port = int(os.environ.get("BRIDGE_LISTEN_PORT", args.listen_port))

    server = ThreadingBridgeServer((host, port), BridgeHandler)
    _vlog(f"Listening on {host}:{port}")
    _vlog(f"DeepSeek base URL: {secrets.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')}")
    has_key = bool(secrets.get("DEEPSEEK_API_KEY"))
    _vlog(f"DeepSeek API key: {'configured' if has_key else 'MISSING — run configure-deepseek.py'}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(file=sys.stderr)
        server.server_close()


if __name__ == "__main__":
    main()
