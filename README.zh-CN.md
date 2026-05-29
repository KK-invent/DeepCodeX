# DeepCodeX

DeepCodeX 是一个面向安全、隐私和可复用性的 DeepCodex 维护工具包。它的目标是让普通 Mac 用户通过 DeepSeek 兼容接口使用 DeepCodeX，同时让维护者可以在不泄露本机配置、不提交上游二进制的前提下构建和升级应用。

当前仓库仍是 private 预览版。它不包含成品 `.app`、`app.asar`、官方 Codex 安装包、真实 API key、登录态、日志、会话、缓存、SQLite 数据库或第三方二进制。

## 你是哪类用户

### 普通用户

如果你只是想下载后直接使用，请等维护者发布私有 Release 成品包，例如 `DeepCodeX.dmg` 或 `DeepCodeX.app.zip`。

普通用户不需要理解补丁过程，只需要准备：

- 一台 macOS 电脑。
- 一个能访问的 DeepSeek / OpenAI-compatible 服务地址。
- 这个服务对应的 API key。

首次启动时填写：

- `DeepSeek base URL`：服务地址，例如 `https://api.deepseek.com`，或你所在环境的内网网关地址。
- `DeepSeek API key`：你的密钥，只在本机保存，不要发给别人，也不要提交到 GitHub。

下载后先运行或查看安装模式检测：

```bash
scripts/detect-install-mode.sh
```

它会把电脑分成四类：

- 已装 DeepCodeX，也已装 Codex：可做 doctor 和版本漂移检查。
- 已装 DeepCodeX，没装 Codex：普通用户成品包路径，只配置 DeepSeek 即可。
- 没装 DeepCodeX，已装 Codex：普通用户可以继续安装成品包；维护者才需要走源码构建路径。
- 两者都没装：普通新用户需要先取得 DeepCodeX 成品包，源码仓库不能直接生成完整 app。

如果电脑没有外网环境，`https://api.deepseek.com` 可能无法访问。这种情况下必须填写你所在网络能访问的内网 DeepSeek 兼容网关，而不是代理地址，也不是 `127.0.0.1:3100`。

### 维护者

如果你要从源码构建 DeepCodeX，需要本机已有官方 Codex desktop app：

```bash
scripts/install-local.sh
scripts/preflight-mac.sh
"$DEEPCODEX_HOME/bin/deepcodex-configure-deepseek.py"
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --stage
```

确认 `--stage` 通过后，才执行：

```bash
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --apply
"$DEEPCODEX_HOME/bin/deepcodex-doctor.py"
```

## 没装 Codex 能不能用

分两种情况：

- 有成品包：可以。下载维护者提供的 DeepCodeX 成品包，运行 `Install-DeepCodeX.command`，按提示填写 DeepSeek base URL 和 API key。
- 只有源码仓库：不可以直接生成完整应用。源码仓库出于合规和隐私原因，不包含官方 Codex app、`app.asar` 或可执行成品。

所以公开前的目标是同时保留两条路径：

- 普通用户路径：下载经过审核的成品包并填写 DeepSeek 配置。
- 维护者路径：从本机官方 Codex app 重新构建、签名、验证，再发布私有成品包。

## 安全边界

- API key 不会打印到终端。
- 真实 `secrets.env`、`auth.json`、`ccx/.config/config.json` 不允许提交。
- 会话、日志、缓存、SQLite 数据库不允许提交。
- 仓库里不放官方 Codex 二进制、上游前端包或第三方二进制。

发布前请运行：

```bash
scripts/audit-release.sh
git status --short
git ls-files
```

更多文档：

- [中文安装指南](docs/INSTALL.zh-CN.md)
- [离线新用户快速指南](docs/OFFLINE_QUICKSTART.zh-CN.md)
- [中文排障指南](docs/TROUBLESHOOTING.zh-CN.md)
- [隐私与安全说明](docs/PRIVACY.zh-CN.md)
- [合规说明](docs/COMPLIANCE.md)
