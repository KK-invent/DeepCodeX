# DeepCodeX 中文排障指南

## 启动前先确认路径

普通用户如果拿到的是 `DeepCodeX-mac.zip`，先解压并双击 `Install-DeepCodeX.command`。安装器会自动检测 Codex、DeepCodeX 和本地 bridge 状态。

如果你想在成品包解压目录里手动看检测结果，运行：

```bash
./support/scripts/detect-install-mode.sh
```

安装完成后再做预检，运行：

```bash
"$HOME/.codex-deepseek/bin/preflight-mac.sh"
```

只有从源码仓库构建或维护的人，才在仓库根目录运行：

```bash
scripts/detect-install-mode.sh
scripts/preflight-mac.sh
```

预检只读取本机状态，不会打印 API key。

## 常见问题

### 1. 没有安装 Codex.app

现象：

```text
missing upstream app: /Applications/Codex.app
```

原因：源码仓库是补丁器，不包含官方 Codex 二进制。

处理：

- 普通用户：先安装官方 Codex desktop app，再运行维护者提供的 DeepCodeX 统一成品包。
- 维护者：先安装官方 Codex desktop app，再运行 `deepcodex-sync-upstream.py --stage`。

如果检测结果是 `[MODE] codex-required` 或 `[MODE] codex-missing-existing-deepcodex`，说明当前机器缺少官方 Codex。安装器会停止并提示官方 Codex 下载页面；补装 Codex 后重新运行安装器。

### 2. 不知道 base URL 填什么

填写你能访问的 DeepSeek / OpenAI-compatible 服务入口。

- 能直连官方 DeepSeek：`https://api.deepseek.com`
- 内网环境：填写内网 DeepSeek 网关
- 不要填写 `127.0.0.1:3100`，这是 DeepCodeX 内部地址

### 3. API key 粘贴后失败

检查：

- key 前后有没有空格
- 是否复制了中文引号
- 是否复制到了多行
- key 是否属于你填写的 base URL 对应服务

脚本会拒绝带空白字符或明显太短的 key。

### 4. 没有代理，是否能用

可以。DeepCodeX 的内部链路会走本地回环地址，不需要代理。

如果你设置过 `HTTP_PROXY`、`HTTPS_PROXY` 或 `ALL_PROXY`，反而可能影响本地回环请求。请确保：

```bash
export NO_PROXY="127.0.0.1,localhost,::1"
export no_proxy="127.0.0.1,localhost,::1"
```

### 5. 完全没外网

如果完全不能访问外部网络，需要满足两个条件：

- 成品包通过内网、U 盘或其他离线方式拿到本机。
- 官方 Codex 安装包也通过内网、U 盘或其他离线方式拿到本机，并安装到 `/Applications/Codex.app`。
- base URL 是本机能访问的内网 DeepSeek 兼容服务。
- 对普通新用户，成品包应使用当前 bridge 版本的 `DeepCodeX-mac.zip`；旧的 no-runtime 包不再作为推荐入口。

如果没有可访问的模型服务，应用可以打开，但无法完成模型请求。

### 6. doctor 报 upstream-version-drift

说明官方 Codex.app 版本和 DeepCodeX 当前应用版本不一致。

维护者处理：

```bash
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --stage
```

预构建通过后再决定是否 `--apply`。

### 7. macOS 提示无法打开

先不要随意绕过安全提示。检查来源和签名：

```bash
codesign --verify --deep --strict "$DEEPCODEX_APP"
```

如果这是维护者私有构建，可能是 ad-hoc 签名。公开发布前应明确签名策略和校验值。

如果是刚从 GitHub 下载的 zip，请先确认 `.sha256` 校验是 `OK`，再右键打开 `Install-DeepCodeX.command`。仍被拦截时，可以对已解压且校验通过的目录执行：

```bash
xattr -dr com.apple.quarantine DeepCodeX-mac
```

不要对来源不明或校验不一致的文件执行 quarantine 移除。

### 8. 发图片后失败

DeepSeek 文本模型不支持原生图片输入。DeepCodeX 通过 image-strip shim 删除或转写图片块，保护主链路。

检查：

```bash
"$DEEPCODEX_HOME/bin/deepcodex-doctor.py"
```

如果 `image-strip` 相关检查失败，先不要继续发图片。
