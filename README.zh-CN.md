<p align="center">
  <img src="assets/brand/deepcodex-hero.svg" alt="DeepCodeX 浅色蓝紫视觉横幅" width="860">
</p>

# DeepCodeX

DeepCodeX 是一个面向安全、隐私和可复用性的 DeepCodex 维护工具包。它的目标是让普通 Mac 用户通过 DeepSeek 兼容接口使用 DeepCodeX，同时让维护者可以在不泄露本机配置、不提交上游二进制的前提下构建和升级应用。

**本仓库不包含成品 `.app`、`app.asar`、官方 Codex 安装包、真实 API key、登录态、日志、会话、缓存、SQLite 数据库或第三方二进制。** 也不再依赖任何私有运行时（ccx 二进制已被纯 Python 翻译层替代）。

视觉素材采用 DeepCodeX 原创图形，不使用 DeepSeek 官方图标。

DeepCodeX 是非官方项目，不隶属于 OpenAI、Codex、DeepSeek 或相关权利方。

## 一张图看懂

![DeepCodeX 本地路由架构](assets/brand/routing-architecture.zh-CN.svg)

![DeepCodeX 统一安装检测流程](assets/brand/install-detection-flow.zh-CN.svg)

![DeepCodeX 安全门禁一览](assets/brand/safety-scorecard.zh-CN.svg)

## 当前链路（已去除私有 ccx）

```
DeepCodex.app ──responses──▶ shim(3100, 剥图) ──▶ bridge(3000, Python翻译) ──▶ DeepSeek(/v1/chat/completions)
```

`bin/deepcodex-deepseek-bridge.py` 是在端口 3000 上运行的开源 Python 服务，替代了之前私有的 `ccx` 二进制。它做三件事：

1. **请求翻译**：把 Codex 的 OpenAI Responses API（`POST /v1/responses`）翻译成 DeepSeek Chat Completions API（`POST /v1/chat/completions`）。
2. **响应翻译**：把 DeepSeek 的流式/非流式响应还原成 Codex 能理解的 Responses 事件流（包含 reasoning、function_call、output_text）。
3. **鉴权转发**：校验本地 `CCX_PROXY_ACCESS_KEY`，替换成你的 `DEEPSEEK_API_KEY` 后转发给 DeepSeek。

零额外依赖——只用 Python 标准库。

## 普通用户安装（无需任何私有二进制）

### 你需要准备

- 一台 macOS 电脑。
- **官方 Codex desktop app**，从 [OpenAI Codex 官方页面](https://openai.com/codex/) 下载并安装到 `/Applications/Codex.app`。
- **一个 DeepSeek API key**，从 [platform.deepseek.com](https://platform.deepseek.com) → API Keys 创建。

### 没有 Codex？先做这一步

DeepCodeX 不自带官方 Codex。先从 [OpenAI Codex 官方页面](https://openai.com/codex/) 安装 Codex，并确认它在 `/Applications/Codex.app`，再继续下面的安装步骤。如果你的 Codex 放在别的位置，运行前先设置 `CODEX_APP=/path/to/Codex.app`。

Codex 官方下载地址：https://openai.com/codex/

### 一步安装

```bash
# 1. 从官方页面下载 Codex.app，安装到 /Applications/Codex.app

# 2. 克隆本仓库
git clone https://github.com/KK-invent/DeepCodeX.git
cd DeepCodeX

# 3. 安装维护工具和本地 bridge 服务
scripts/install-local.sh

# 4. 填写你自己的 DeepSeek base URL 和 API key
~/.codex-deepseek/bin/deepcodex-configure-deepseek.py --restart-services

# 5. 从本地 Codex 构建 DeepCodeX
~/.codex-deepseek/bin/deepcodex-sync-upstream.py --stage   # 预检
~/.codex-deepseek/bin/deepcodex-sync-upstream.py --apply   # 构建

# 6. 以后也可以在 DeepCodeX.app 菜单里打开"配置 DeepSeek..."修改配置

# 7. 验证
~/.codex-deepseek/bin/deepcodex-doctor.py     # 期望 FAIL=0
```

> **全程不需要向任何人索要私有二进制或密钥**。你的 API key 只保存在本机 `~/.codex-deepseek/secrets.env` 中，不会发送给任何人。

### 配置 DeepSeek 的两种方式

**方式一（源码首次安装推荐）：命令行配置**

```bash
~/.codex-deepseek/bin/deepcodex-configure-deepseek.py --restart-services
```

按提示填写：

- `DeepSeek base URL`：默认 `https://api.deepseek.com`，除非你使用内网或第三方 OpenAI-compatible 网关。
- `DeepSeek API key`：从 [platform.deepseek.com](https://platform.deepseek.com) → API Keys 创建后粘贴。

配置会写入本机 `~/.codex-deepseek/secrets.env`，不会打印 key。

**方式二：DeepCodeX 应用内**

1. 首次启动 DeepCodeX.app 时，自动弹出"配置 DeepSeek"窗口。
2. 填写 **DeepSeek base URL**（默认 `https://api.deepseek.com`）和 **DeepSeek API key**（密码框）。
3. 点击"保存并重启"。
4. 之后也可以从菜单栏 **「配置 DeepSeek...」**(Configure DeepSeek...) 随时修改。

或直接编辑 `~/.codex-deepseek/secrets.env`，设置：

```bash
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=sk-你的key
```

然后重启 bridge 服务：

```bash
launchctl kickstart gui/$(id -u)/com.deepcodex.deepseek-bridge
```

## 维护者

如果你要从源码构建 DeepCodeX，需要本机已有官方 Codex desktop app：

```bash
scripts/install-local.sh
scripts/preflight-mac.sh
"$DEEPCODEX_HOME/bin/deepcodex-configure-deepseek.py" --restart-services
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --stage
# --stage 通过后:
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --apply
"$DEEPCODEX_HOME/bin/deepcodex-doctor.py"
```

## 安全边界

- API key 不会打印到终端。
- 真实 `secrets.env`、`auth.json` 不允许提交。
- 会话、日志、缓存、SQLite 数据库不允许提交。
- 仓库里不放官方 Codex 二进制、上游前端包或第三方二进制。
- 源码、原创文档和原创视觉素材采用 MIT License；该许可证不授予任何上游应用、商标、服务账号、API key 或第三方资产的权利。

发布前请运行：

```bash
scripts/audit-release.sh
```

更多文档：

- [中文安装指南](docs/INSTALL.zh-CN.md)
- [离线新用户快速指南](docs/OFFLINE_QUICKSTART.zh-CN.md)
- [中文排障指南](docs/TROUBLESHOOTING.zh-CN.md)
- [隐私与安全说明](docs/PRIVACY.zh-CN.md)
- [合规说明](docs/COMPLIANCE.md)
- [贡献指南](CONTRIBUTING.md)
- [支持说明](SUPPORT.md)
- [安全策略](SECURITY.md)
- [更新记录](CHANGELOG.md)
