# DeepCodeX 私有预览包

这是给私有仓库成员下载验证的预览发行，不是公开 release。

## 推荐下载

完全没有安装 Codex 的普通 Mac 用户，优先下载：

- `DeepCodeX-private-with-local-ccx-*.zip`
- 对应的 `.zip.sha256`

这个包包含本地转发 runtime，更接近解压后直接安装使用。

## 保守包

`DeepCodeX-private-no-ccx-*.zip` 不包含本地转发 runtime。它适合维护者或已经有兼容 runtime 的机器，不适合完全新用户单独使用。

## 安装

1. 下载 zip 和对应 `.sha256`。
2. 如果会使用终端，先运行 `shasum -a 256 -c <文件名>.sha256`。
3. 解压 zip。
4. 双击 `Install-DeepCodeX.command`。
5. 按提示填写 `DeepSeek base URL` 和 `DeepSeek API key`。

无外网环境下，`base URL` 要填写这台 Mac 能访问的内网 DeepSeek / OpenAI-compatible 网关。不要填写 `127.0.0.1:3100`，那是 DeepCodeX 内部地址。

如果 macOS 阻止打开，请先确认 `.sha256` 校验是 `OK`，再右键打开安装脚本。仍被拦截时，只对校验通过的解压目录执行 `xattr -dr com.apple.quarantine DeepCodeX-private-with-local-ccx-*`。

## 安全边界

- 安装脚本不会打印 API key。
- 包审计会检查真实本机 key、运行态数据库、日志、会话文件和维护者路径。
- `with-local-ccx` 包包含本地 runtime，只适合私有、已审阅的分发场景。
