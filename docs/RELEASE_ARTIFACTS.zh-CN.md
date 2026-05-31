# 私有成品包计划

目标：让普通 Mac 用户通过一个统一私有成品包安装 DeepCodeX。安装器自己检测是否存在官方 Codex；缺失时明确引导用户先安装 Codex，而不是让用户在“有 Codex 版”和“无 Codex 版”之间选择。

## 当前状态

源码仓库不包含成品 app，也不包含官方 Codex 二进制。这是为了降低泄露风险和合规风险。

公开源码仓库适合能运行命令行的用户和维护者。普通用户如果不想从源码构建，可以使用维护者私下提供的统一成品包。

## 普通用户成品包应包含

- `Deepcodex.app`
- `Install-DeepCodeX.command`
- 极简蓝鲸视觉资产和说明图
- 首次启动配置窗口
- 安装前环境检测输出：已装 Codex、缺少 Codex、已装 DeepCodeX 等状态要说清楚
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
- 官方 Codex 安装包或 OpenAI/Codex 官方商标素材
- 未记录来源和使用边界的第三方官方视觉素材

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
- 缺少 Codex 时安装器停止，并指向官方 Codex 页面。
- 模型菜单只出现 DeepSeek 相关模型。
- 没有 ChatGPT OAuth token。
- 成品包不包含维护者的运行态目录。
- 成品包内 `Info.plist` 不包含维护者的 `CCX_PROXY_ACCESS_KEY`、`CODEX_HOME` 或 `CODEX_ELECTRON_USER_DATA_PATH`。
- 成品包内 `app.asar` 不包含维护者本机路径。
- `assets/brand/SOURCES.md` 已记录视觉素材来源；公开源码默认只保留原创 DeepCodeX 视觉素材。

## 打包命令

面向普通用户的私有预览包：

```bash
scripts/package-private-release.sh
```

输出文件名是 `DeepCodeX-mac.zip`。这是默认推荐给普通用户的统一包。`--bundle-runtime` 已弃用；当前包使用仓库内置 Python bridge，不再包含或要求私有 `ccx` runtime。

如果要从 staged app 打包，而不是从 `/Applications/Deepcodex.app` 打包：

```bash
DEEPCODEX_APP=/Applications/Deepcodex.app.tmp-controlled-upgrade-YYYYMMDD-HHMMSS scripts/package-private-release.sh
```

打包脚本会调用 `scripts/audit-package.sh`。如果当前 app 里还残留维护者路径或真实本机 key，打包会失败。

分享 `DeepCodeX-mac.zip` 统一包前，额外运行：

```bash
scripts/smoke-offline-package.sh dist/private/DeepCodeX-mac.zip
```

这个 smoke test 会解压包、模拟没有 Codex 的新机器、检查安装器缺 Codex 时会停止、检查 Python bridge 支持文件、用假的 base URL/API key 配置临时 app，并确认输出不泄露 key。

## 上传私有 GitHub Release

确认本地包和校验文件存在后：

```bash
scripts/publish-private-release.sh
```

如果是在更新已有的 `private-preview-*` Release，且同名 git tag 还指向旧 commit，确认这个私有预览 tag 应该移动后再加 `--retarget-tag`：

```bash
scripts/publish-private-release.sh --retarget-tag
```

这个脚本会先确认 GitHub 仓库是 private，再运行源码审计、完整离线安装 smoke、SHA256 校验，让 Release tag 对齐本次发布 commit，然后创建或更新 prerelease。不要把 `DeepCodeX-mac.zip` 成品包上传到公开仓库。

上传完成后脚本还会确认 Release 里只暴露预期的简洁资产名。普通用户 Release 应只有：

```text
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
```

如果是复查已经存在的 Release，可以手动运行：

```bash
scripts/verify-release-assets.sh --tag private-preview-YYYYMMDD-HHMMSS --expected-target $(git rev-parse HEAD)
```

`.sha256` 文件只能包含 zip 文件名，不能包含维护者本机绝对路径。`scripts/publish-private-release.sh` 会拒绝带维护者路径或用户名的校验文件。`scripts/verify-release-assets.sh` 还会比对 GitHub 返回的 zip asset digest 和 `.sha256` 内容，避免远端 zip 与校验文件不一致。

## 无外网用户怎么使用

无外网用户不能从 GitHub 下载，也不能访问官方 DeepSeek。需要通过内网、U 盘或其他离线方式获得：

1. 官方 Codex 安装包。
2. DeepCodeX 统一成品包。
3. 内网可访问的 DeepSeek 兼容网关 base URL。

如果没有可访问的模型服务，应用只能启动，不能完成推理请求。
