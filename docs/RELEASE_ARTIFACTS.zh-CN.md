# 私有成品包计划

目标：让没有安装 Codex、没有代理、没有外网环境的普通 Mac 用户，也能通过一个私有成品包安装 DeepCodeX，并清楚知道如何填写 DeepSeek base URL 和 API key。

## 当前状态

源码仓库不包含成品 app，也不包含官方 Codex 二进制。这是为了降低泄露风险和合规风险。

因此当前 private 仓库适合维护者，不适合直接给普通用户下载使用。

## 普通用户成品包应包含

- `Deepcodex.app`
- 首次启动配置窗口
- 清晰的中文说明
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
```

还需要手动检查：

- 首次启动时缺配置会弹出 DeepSeek 配置窗口。
- API key 输入框不会明文显示。
- 保存后不会把 API key 打印到日志或终端。
- 模型菜单只出现 DeepSeek 相关模型。
- 没有 ChatGPT OAuth token。
- 成品包不包含维护者的运行态目录。

## 无外网用户怎么使用

无外网用户不能从 GitHub 下载，也不能访问官方 DeepSeek。需要通过内网、U 盘或其他离线方式获得成品包，并填写内网可访问的 DeepSeek 兼容网关 base URL。

如果没有可访问的模型服务，应用只能启动，不能完成推理请求。
