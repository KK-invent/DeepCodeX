# DeepCodeX 中文安装指南

> **2026-05-30 更新**：DeepCodeX 翻译层已从私有 ccx 二进制替换为开源 Python bridge（`bin/deepcodex-deepseek-bridge.py`），零额外依赖。
> 任何只要装了官方 Codex.app、有 DeepSeek API key 的人都能开箱即用，无需向维护者索要私有组件。
> 详见 [README.zh-CN.md](../README.zh-CN.md) 的新安装流程。

## 先确认一个事实

DeepCodeX 使用 DeepSeek 兼容接口，不需要 ChatGPT OAuth 登录。但它仍然需要能访问某个 DeepSeek / OpenAI-compatible 服务。

如果你的 Mac 完全没有外网，也没有内网 DeepSeek 网关，那么只填写 API key 也无法使用。你需要先拿到一个本机能访问的 base URL。

## 需要填写什么

首次配置只需要两个值：

### DeepSeek base URL

这是 DeepSeek 兼容服务的入口地址。

常见情况：

- 能直连官方 DeepSeek：`https://api.deepseek.com`
- 使用公司或团队内网网关：填写管理员给你的 HTTPS 地址，例如 `https://deepseek.example.internal`
- 使用本地测试网关：填写你实际可访问的 HTTP/HTTPS 地址

不要填写：

- `127.0.0.1:3100`
- `localhost:3100`
- Clash、Surge、V2Ray 等代理地址
- GitHub 地址
- DeepSeek 网页聊天地址

`127.0.0.1:3100` 是 DeepCodeX 内部 shim 地址，用户不需要填写。

### DeepSeek API key

这是服务提供方给你的密钥。它只保存在本机配置里，不应发给别人，也不应提交到 GitHub。

## 公开源码安装路径

适用于从 GitHub 公开仓库安装：

```bash
git clone https://github.com/KK-invent/DeepCodeX.git
cd DeepCodeX
scripts/install-local.sh
"$HOME/.codex-deepseek/bin/deepcodex-configure-deepseek.py" --restart-services
"$HOME/.codex-deepseek/bin/deepcodex-sync-upstream.py" --stage
"$HOME/.codex-deepseek/bin/deepcodex-sync-upstream.py" --apply
"$HOME/.codex-deepseek/bin/deepcodex-doctor.py"
```

`deepcodex-configure-deepseek.py` 会提示你填写 `DeepSeek base URL` 和 `DeepSeek API key`。如果你能直连官方 DeepSeek，base URL 使用默认值 `https://api.deepseek.com` 即可。`--restart-services` 会让本地 bridge 立刻读取新配置。

## 私有成品包安装路径

适用于维护者已经提供私有 Release 成品包的情况。推荐下载：

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

DeepCodeX 不再区分“有 Codex 版”和“无 Codex 版”。同一个安装包会先检测 `/Applications/Codex.app`。如果没有检测到官方 Codex，安装器会停止，并引导你去 [OpenAI Codex 官方页面](https://openai.com/codex/) 下载 Codex。

下载后先校验文件：

```bash
shasum -a 256 -c DeepCodeX-mac.zip.sha256
```

1. 下载 `DeepCodeX-mac.zip` 和 `DeepCodeX-mac.zip.sha256`。
2. 在同一目录运行上面的校验命令，确认输出是 `OK`。
3. 解压 `DeepCodeX-mac.zip`。
4. 双击 `Install-DeepCodeX.command`。
5. 先看安装脚本输出的环境检测结果：
   - 已安装 Codex：可以继续安装，DeepCodeX 使用独立目录，不覆盖原 Codex。
   - 未安装 Codex：先安装官方 Codex，再重新运行 `Install-DeepCodeX.command`。
6. 按安装脚本提示，或在应用菜单 **「配置 DeepSeek...」** 中填写：
   - `DeepSeek base URL`
   - `DeepSeek API key`
7. 安装完成后打开 `/Applications/Deepcodex.app`。
8. 进入应用后确认模型菜单只出现 DeepSeek 相关模型。

`scripts/detect-install-mode.sh` 是源码仓库里的维护者辅助脚本。普通下载用户不需要手动运行它；成品包内的安装器会自动执行同等检测。

如果 macOS 提示应用来自未知开发者，先不要绕过。请确认成品包来源、校验值和维护者说明。

## 维护者构建路径

适用于从源码仓库构建。

```bash
git clone https://github.com/KK-invent/DeepCodeX.git
cd DeepCodeX
scripts/audit-release.sh
scripts/install-local.sh
scripts/preflight-mac.sh
```

先配置 DeepSeek，再预构建。`--stage` 会跑本地 DeepSeek smoke test，因此不能在 key 为空时执行：

```bash
"$DEEPCODEX_HOME/bin/deepcodex-configure-deepseek.py" --restart-services
```

预构建：

```bash
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --stage
```

只有预构建通过后才替换本机 app：

```bash
"$DEEPCODEX_HOME/bin/deepcodex-sync-upstream.py" --apply
"$DEEPCODEX_HOME/bin/deepcodex-doctor.py"
```

## 没有 Codex.app 怎么办

如果你是普通用户：先安装官方 Codex desktop app，再运行维护者发布的 DeepCodeX 成品包。

如果这台 Mac 没有外网：在有网机器从官方页面取得 Codex 安装包，再通过内网或 U 盘传入这台 Mac。安装完成后确认 `/Applications/Codex.app` 存在。

如果你是维护者：需要先安装官方 Codex desktop app，或者在合规允许的私有环境里准备一个可审计的 DeepCodeX 成品包。当前源码仓库不会附带官方 Codex 二进制。

## 没有代理怎么办

DeepCodeX 不要求代理。更推荐直接访问 DeepSeek 或你的内网网关。

如果你的网络能访问 `https://api.deepseek.com`，base URL 就填它。

如果不能访问官方 DeepSeek，但能访问公司内网网关，base URL 填公司内网网关。

如果两者都不能访问，DeepCodeX 无法发起模型请求，需要先解决网络或服务入口问题。
