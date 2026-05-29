# DeepCodeX 中文安装指南

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

## 普通用户安装路径

适用于维护者已经提供 `DeepCodeX.dmg` 或 `DeepCodeX.app.zip` 的情况。

如果这台 Mac 没有安装 Codex，也没有外网，优先使用文件名包含 `with-local-ccx` 的成品包。文件名包含 `no-ccx` 的包可以安装应用外壳，但普通新用户还需要另外取得兼容 runtime。

先识别当前电脑状态：

```bash
scripts/detect-install-mode.sh
```

1. 下载成品包。
2. 打开或解压。
3. 双击 `Install-DeepCodeX.command`。
4. 先看安装脚本输出的环境检测结果：
   - 已安装 Codex：可以继续安装，DeepCodeX 使用独立目录，不覆盖原 Codex。
   - 未安装 Codex：也可以继续安装成品包，不需要先理解或安装 Codex。
5. 按安装脚本提示填写：
   - `DeepSeek base URL`
   - `DeepSeek API key`
6. 安装完成后打开 `/Applications/Deepcodex.app`。
7. 进入应用后确认模型菜单只出现 DeepSeek 相关模型。

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

配置 DeepSeek：

```bash
"$DEEPCODEX_HOME/bin/deepcodex-configure-deepseek.py"
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

如果你是普通用户：使用维护者发布的成品包。

如果你是维护者：需要先安装官方 Codex desktop app，或者在合规允许的私有环境里准备一个可审计的 DeepCodeX 成品包。当前源码仓库不会附带官方 Codex 二进制。

## 没有代理怎么办

DeepCodeX 不要求代理。更推荐直接访问 DeepSeek 或你的内网网关。

如果你的网络能访问 `https://api.deepseek.com`，base URL 就填它。

如果不能访问官方 DeepSeek，但能访问公司内网网关，base URL 填公司内网网关。

如果两者都不能访问，DeepCodeX 无法发起模型请求，需要先解决网络或服务入口问题。
