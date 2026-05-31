# DeepCodeX 私有预览包

这是给私有仓库成员下载验证的预览发行，不是公开 release。

## 推荐下载

普通 Mac 用户只需要下载统一包：

- `DeepCodeX-mac.zip`
- `DeepCodeX-mac.zip.sha256`

这个包包含开源 Python bridge 支持文件，并会自动检测 `/Applications/Codex.app`。如果没有检测到官方 Codex，安装器会停止并引导你先去官方页面下载 Codex；不需要另找“无 Codex 版”。

## 安装

1. 下载 zip 和对应 `.sha256`。
2. 如果会使用终端，先运行 `shasum -a 256 -c <文件名>.sha256`。
3. 解压 zip。
4. 双击 `Install-DeepCodeX.command`。
5. 如果提示缺少 Codex，先安装官方 Codex 后重新运行安装器。
6. 按提示填写 `DeepSeek base URL` 和 `DeepSeek API key`。

无外网环境下，`base URL` 要填写这台 Mac 能访问的内网 DeepSeek / OpenAI-compatible 网关。不要填写 `127.0.0.1:3100`，那是 DeepCodeX 内部地址。

如果 macOS 阻止打开，请先确认 `.sha256` 校验是 `OK`，再右键打开安装脚本。仍被拦截时，只对校验通过的解压目录执行 `xattr -dr com.apple.quarantine DeepCodeX-mac`。

## 安全边界

- 安装脚本不会打印 API key。
- 包审计会检查真实本机 key、运行态数据库、日志、会话文件和维护者路径。
- `DeepCodeX-mac.zip` 不包含私有 `ccx` runtime；它使用仓库内置 Python bridge。
