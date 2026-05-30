<p align="center">
  <img src="assets/brand/deepseek-app-icon.png" alt="DeepSeek 蓝鲸应用图标" width="156">
</p>

<p align="center">
  <img src="assets/brand/deepcodex-logo.zh-CN.svg" alt="DeepCodeX 中文标志" width="560">
</p>

# DeepCodeX

DeepCodeX 是一个面向安全、隐私和可复用性的 DeepCodex 维护工具包。它的目标是让普通 Mac 用户通过 DeepSeek 兼容接口使用 DeepCodeX，同时让维护者可以在不泄露本机配置、不提交上游二进制的前提下构建和升级应用。

当前仓库仍是 private 预览版。它不包含成品 `.app`、`app.asar`、官方 Codex 安装包、真实 API key、登录态、日志、会话、缓存、SQLite 数据库或第三方二进制。

视觉素材采用 DeepSeek 官网公开 App 图标的蓝鲸风格；素材来源和商标边界见 [assets/brand/SOURCES.md](assets/brand/SOURCES.md) 与 [docs/COMPLIANCE.md](docs/COMPLIANCE.md)。

DeepCodeX 是非官方 private 预览项目，不隶属于 OpenAI、Codex、DeepSeek 或相关权利方，也不代表这些权利方的认可、背书或支持。

## 一张图看懂

![DeepCodeX 本地路由架构](assets/brand/routing-architecture.zh-CN.svg)

![DeepCodeX 统一安装检测流程](assets/brand/install-detection-flow.zh-CN.svg)

![DeepCodeX 安全门禁一览](assets/brand/safety-scorecard.zh-CN.svg)

## 你是哪类用户

### 普通用户

如果你只是想下载后直接使用，请下载维护者发布的私有 Release 成品包。面向普通用户的推荐文件名形如：

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

DeepCodeX 不再区分“有 Codex 版”和“无 Codex 版”。同一个安装包会先检测 `/Applications/Codex.app`：

- 已安装 Codex：继续安装 DeepCodeX，不覆盖原 Codex。
- 未安装 Codex：安装器会停止，并引导你先去 [OpenAI Codex 官方页面](https://openai.com/codex/) 下载 Codex。

普通用户不需要理解补丁过程，只需要准备：

- 一台 macOS 电脑。
- 官方 Codex desktop app，安装位置通常是 `/Applications/Codex.app`。
- 一个能访问的 DeepSeek / OpenAI-compatible 服务地址。
- 这个服务对应的 API key。

首次启动时填写：

- `DeepSeek base URL`：服务地址，例如 `https://api.deepseek.com`，或你所在环境的内网网关地址。
- `DeepSeek API key`：你的密钥，只在本机保存，不要发给别人，也不要提交到 GitHub。

下载后的普通用户路径：

```bash
shasum -a 256 -c DeepCodeX-mac.zip.sha256
```

校验通过后解压 `DeepCodeX-mac.zip`，双击 `Install-DeepCodeX.command`。安装器会自动运行环境检测，并把电脑分成四类：

- 已装 DeepCodeX，也已装 Codex：可做 doctor 和版本漂移检查。
- 已装 DeepCodeX，没装 Codex：先补装官方 Codex，再重新运行安装器或 doctor。
- 没装 DeepCodeX，已装 Codex：普通用户可以继续安装成品包；维护者才需要走源码构建路径。
- 两者都没装：先安装官方 Codex，再运行 DeepCodeX 成品包；源码仓库不能直接生成完整 app。

只有维护者或从源码仓库调试的人需要手动运行：

```bash
scripts/detect-install-mode.sh
```

如果电脑没有外网环境，`https://api.deepseek.com` 可能无法访问。这种情况下必须填写你所在网络能访问的内网 DeepSeek 兼容网关，而不是代理地址，也不是 `127.0.0.1:3100`。

如果电脑没有外网且还没安装 Codex，请先在有网机器从官方页面取得 Codex 安装包，再通过内网或 U 盘传入。

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

同一个 DeepCodeX 安装包会自动检测，不需要用户自己选“有 Codex 版”或“无 Codex 版”。

- 有成品包，但没装 Codex：安装器会提示你先安装官方 Codex。补装后重新运行 `Install-DeepCodeX.command`。
- 只有源码仓库：不可以直接生成完整应用。源码仓库出于合规和隐私原因，不包含官方 Codex app、`app.asar` 或可执行成品。

所以项目保留两条路径：

- 普通用户路径：下载经过审核的统一成品包，安装器自动检测 Codex，之后填写 DeepSeek 配置。
- 维护者路径：从本机官方 Codex app 重新构建、签名、验证，再发布私有成品包。

## 安全边界

- API key 不会打印到终端。
- 真实 `secrets.env`、`auth.json`、`ccx/.config/config.json` 不允许提交。
- 会话、日志、缓存、SQLite 数据库不允许提交。
- 仓库里不放官方 Codex 二进制、上游前端包或第三方二进制。

发布前请运行：

```bash
scripts/audit-release.sh
scripts/audit-public-release.sh --repo KK-invent/DeepCodeX
git status --short
git ls-files
```

更新 GitHub 私有 Release 后，请确认远端只暴露简洁资产名：

```bash
scripts/verify-release-assets.sh --tag private-preview-YYYYMMDD-HHMMSS
```

更多文档：

- [中文安装指南](docs/INSTALL.zh-CN.md)
- [离线新用户快速指南](docs/OFFLINE_QUICKSTART.zh-CN.md)
- [中文排障指南](docs/TROUBLESHOOTING.zh-CN.md)
- [隐私与安全说明](docs/PRIVACY.zh-CN.md)
- [合规说明](docs/COMPLIANCE.md)
- [公开发布检查清单](docs/PUBLIC_RELEASE_CHECKLIST.md)
- [更新记录](CHANGELOG.md)
