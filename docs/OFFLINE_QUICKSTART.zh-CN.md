# DeepCodeX 离线新用户快速指南

适用对象：这台 Mac 没有外网或代理，但可以通过内网、U 盘或其他方式拿到安装包，并且能访问某个内网 DeepSeek / OpenAI-compatible 服务。

## 你需要先拿到什么

1. 官方 Codex desktop app 安装包。请从 [OpenAI Codex 官方页面](https://openai.com/codex/) 获取；如果这台 Mac 没外网，就在有网机器下载后传入。
2. DeepCodeX 公开源码 zip，或维护者提供的私有统一成品包。
3. 如果是私有成品包，还需要对应的 `.sha256` 校验文件。
4. 一个这台 Mac 能访问的 `DeepSeek base URL`。
5. 这个服务对应的 `DeepSeek API key`。

如果你完全没有可访问的模型服务，只拿到 API key 也不能使用。DeepCodeX 可以离线安装，但模型请求必须发到一个本机能访问的服务入口。

## 应该下载哪个 DeepCodeX 包

公开合规路径优先使用 GitHub 自动生成的源码 zip。它不包含官方 Codex，也不包含预构建 Deepcodex.app；解压后双击根目录里的 `Install-DeepCodeX.command`，安装器会从本机已有 Codex.app 构建 DeepCodeX。

如果维护者另行提供私有成品包，普通用户只需要一个统一包，推荐文件名形如：

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

这个包会自动检测 Codex。它不是“有 Codex 版”或“无 Codex 版”二选一；如果检测不到 `/Applications/Codex.app`，安装器会先提示你安装官方 Codex。

旧的 `DeepCodeX-mac-no-runtime.zip` 命名已经不再适合作为普通用户入口。当前链路使用仓库内置的 Python bridge，不需要额外索要私有 runtime。

## base URL 填什么

填写模型服务入口地址。

可以填写：

- 能直连官方 DeepSeek 时：`https://api.deepseek.com`
- 无外网但有内网服务时：管理员给你的内网 HTTPS 地址，例如 `https://deepseek.example.internal`
- 本地部署了兼容服务时：该服务真实监听的 HTTP/HTTPS 地址

不要填写：

- `127.0.0.1:3100`
- `localhost:3100`
- Clash、Surge、V2Ray 等代理地址
- GitHub 下载地址
- DeepSeek 网页聊天地址

`127.0.0.1:3100` 是 DeepCodeX 内部地址，不是用户要填的上游服务地址。

## API key 填什么

填写上面那个 base URL 对应服务发给你的 key。

不要填写：

- GitHub token
- OpenAI key，除非你的内网网关明确要求使用它
- 代理软件密码
- 网页登录密码

DeepCodeX 安装脚本不会把 API key 打印到终端，也不会上传给维护者。

## 安装步骤

### 公开源码 zip

1. 先安装官方 Codex，并确认 `/Applications/Codex.app` 存在。
2. 把 GitHub 下载的 DeepCodeX 源码 zip 传到这台 Mac。
3. 完整解压源码 zip。
4. 双击 `Install-DeepCodeX.command`。
5. 按提示填写 `DeepSeek base URL` 和 `DeepSeek API key`。
6. 安装完成后打开 `/Applications/Deepcodex.app`。

### 私有成品包

1. 先安装官方 Codex，并确认 `/Applications/Codex.app` 存在。
2. 把 DeepCodeX 成品包和 `.sha256` 文件放到同一个文件夹。
3. 如果你会使用终端，可以先校验：

   ```bash
   shasum -a 256 -c DeepCodeX-mac.zip.sha256
   ```

   看到 `OK` 再继续。

4. 解压 DeepCodeX 成品包。
5. 双击 `Install-DeepCodeX.command`。
6. 看到环境检测结果后继续安装。
7. 按提示填写 `DeepSeek base URL` 和 `DeepSeek API key`。
8. 安装完成后打开 `/Applications/Deepcodex.app`。

## macOS 提示无法打开

如果双击 `Install-DeepCodeX.command` 或打开 app 时提示“无法打开”：

1. 先确认 zip 的 `.sha256` 校验是 `OK`。
2. 确认文件来自维护者给你的私有 Release。
3. 右键点击 `Install-DeepCodeX.command`，选择“打开”。

如果仍然被拦截，并且你已经确认来源和校验值，可以在终端对解压后的目录执行：

```bash
xattr -dr com.apple.quarantine DeepCodeX-mac
```

不要对来源不明或校验不一致的文件执行这一步。

## 看到 Codex 缺失提示怎么办

如果安装器提示没有检测到官方 Codex：

1. 先安装官方 Codex。
2. 确认 `/Applications/Codex.app` 存在。
3. 重新双击 `Install-DeepCodeX.command`。

DeepCodeX 统一包会主动检测，不需要你重新下载另一个“无 Codex 版”。

## 现在不需要私有运行时了

DeepCodeX 已不再依赖私有 ccx 二进制。翻译层 `bin/deepcodex-deepseek-bridge.py` 是开源 Python 脚本，包含在仓库内。

如果安装器提示旧 runtime 缺失，说明拿到的不是当前 bridge 版本安装包。请改用包含 `deepcodex-deepseek-bridge.py` 的新包，或从公开源码运行 `scripts/install-local.sh`。

## 安装后仍不可用

先确认三件事：

1. 这台 Mac 能访问你填写的 base URL。
2. API key 属于这个 base URL 对应的服务。
3. `/Applications/Codex.app` 和 `/Applications/Deepcodex.app` 都存在。

如果还失败，把下面命令的输出发给维护者。输出不会打印 API key：

```bash
"$HOME/.codex-deepseek/bin/deepcodex-doctor.py"
```
