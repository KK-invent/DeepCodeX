# DeepCodeX 离线新用户快速指南

适用对象：这台 Mac 没有安装 Codex，也没有外网或代理，但可以访问某个内网 DeepSeek / OpenAI-compatible 服务。

## 你需要先拿到什么

1. 维护者提供的成品包。
2. 成品包对应的 `.sha256` 校验文件。
3. 一个这台 Mac 能访问的 `DeepSeek base URL`。
4. 这个服务对应的 `DeepSeek API key`。

如果你完全没有可访问的模型服务，只拿到 API key 也不能使用。DeepCodeX 可以离线安装，但模型请求必须发到一个本机能访问的服务入口。

## 应该下载哪个包

- 文件名包含 `with-local-ccx`：适合完全没有 Codex 的新用户，包内带运行所需的本地转发 runtime。
- 文件名包含 `no-ccx`：适合维护者或已经有兼容 runtime 的机器。普通新用户不建议使用这个包。

如果你不确定，优先向维护者索要 `with-local-ccx` 包。

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

1. 把成品包和 `.sha256` 文件放到同一个文件夹。
2. 如果你会使用终端，可以先校验：

   ```bash
   shasum -a 256 -c DeepCodeX-private-with-local-ccx-*.zip.sha256
   ```

   看到 `OK` 再继续。

3. 解压成品包。
4. 双击 `Install-DeepCodeX.command`。
5. 看到环境检测结果后继续安装。
6. 按提示填写 `DeepSeek base URL` 和 `DeepSeek API key`。
7. 安装完成后打开 `/Applications/Deepcodex.app`。

## macOS 提示无法打开

如果双击 `Install-DeepCodeX.command` 或打开 app 时提示“无法打开”：

1. 先确认 zip 的 `.sha256` 校验是 `OK`。
2. 确认文件来自维护者给你的私有 Release。
3. 右键点击 `Install-DeepCodeX.command`，选择“打开”。

如果仍然被拦截，并且你已经确认来源和校验值，可以在终端对解压后的目录执行：

```bash
xattr -dr com.apple.quarantine DeepCodeX-private-with-local-ccx-*
```

不要对来源不明或校验不一致的文件执行这一步。

## 看到 runtime 警告怎么办

如果安装器提示：

```text
package does not contain ccx runtime
```

说明你拿到的是 `no-ccx` 包。它可以安装应用外壳，但普通新用户还不能直接发起模型请求。请向维护者索要 `with-local-ccx` 包，或让维护者补齐兼容 runtime。

## 安装后仍不可用

先确认三件事：

1. 这台 Mac 能访问你填写的 base URL。
2. API key 属于这个 base URL 对应的服务。
3. 你拿到的是 `with-local-ccx` 包，或者本机已有兼容 runtime。

如果还失败，把下面命令的输出发给维护者。输出不会打印 API key：

```bash
"$HOME/.codex-deepseek/bin/deepcodex-doctor.py"
```
