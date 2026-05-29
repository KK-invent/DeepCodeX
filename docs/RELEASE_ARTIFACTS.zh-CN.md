# 私有成品包计划

目标：让没有安装 Codex、没有代理、没有外网环境的普通 Mac 用户，也能通过一个私有成品包安装 DeepCodeX，并清楚知道如何填写 DeepSeek base URL 和 API key。

## 当前状态

源码仓库不包含成品 app，也不包含官方 Codex 二进制。这是为了降低泄露风险和合规风险。

因此当前 private 仓库适合维护者，不适合直接给普通用户下载使用。

## 普通用户成品包应包含

- `Deepcodex.app`
- `Install-DeepCodeX.command`
- 首次启动配置窗口
- 安装前环境检测输出：已装 Codex、已装 DeepCodeX、两者都没有三类情况要说清楚
- 清晰的中文说明
- 离线新用户快速指南
- 校验值
- 版本号
- 已知问题

不应包含：

- 维护者的 API key
- 维护者的 `auth.json`
- 维护者的日志、会话、缓存、SQLite 数据库
- 维护者的用户目录路径

## 成品包发布前门禁

维护者在私有环境内构建后，至少检查：

```bash
scripts/audit-release.sh
"$DEEPCODEX_HOME/bin/deepcodex-doctor.py"
codesign --verify --deep --strict "$DEEPCODEX_APP"
scripts/package-private-release.sh
```

还需要手动检查：

- 首次启动时缺配置会弹出 DeepSeek 配置窗口。
- API key 输入框不会明文显示。
- 保存后不会把 API key 打印到日志或终端。
- 模型菜单只出现 DeepSeek 相关模型。
- 没有 ChatGPT OAuth token。
- 成品包不包含维护者的运行态目录。
- 成品包内 `Info.plist` 不包含维护者的 `CCX_PROXY_ACCESS_KEY`、`CODEX_HOME` 或 `CODEX_ELECTRON_USER_DATA_PATH`。
- 成品包内 `app.asar` 不包含维护者本机路径。

## 打包命令

默认不包含本地 `ccx` 二进制：

```bash
scripts/package-private-release.sh
```

输出文件名包含 `no-ccx`。这种包适合保守分发，但普通用户还需要另外取得兼容的 `ccx` runtime。

如果是在 private 分发环境，且已经确认 `ccx` 二进制的再分发边界，可以显式包含：

```bash
scripts/package-private-release.sh --include-local-ccx
```

输出文件名包含 `with-local-ccx`。这种包才更接近“没装 Codex 的用户解压后直接安装使用”，但不要在公开 release 中默认分发。

如果要从 staged app 打包，而不是从 `/Applications/Deepcodex.app` 打包：

```bash
DEEPCODEX_APP=/Applications/Deepcodex.app.tmp-controlled-upgrade-YYYYMMDD-HHMMSS scripts/package-private-release.sh
```

打包脚本会调用 `scripts/audit-package.sh`。如果当前 app 里还残留维护者路径或真实本机 key，打包会失败。

## 上传私有 GitHub Release

确认本地包和校验文件存在后：

```bash
scripts/publish-private-release.sh --include-with-local-ccx
```

这个脚本会先确认 GitHub 仓库是 private，再运行源码审计、包审计和 SHA256 校验，然后创建或更新 prerelease。不要把 `with-local-ccx` 上传到公开仓库。

## 无外网用户怎么使用

无外网用户不能从 GitHub 下载，也不能访问官方 DeepSeek。需要通过内网、U 盘或其他离线方式获得成品包，并填写内网可访问的 DeepSeek 兼容网关 base URL。

如果没有可访问的模型服务，应用只能启动，不能完成推理请求。
