# DeepCodeX 隐私与安全说明

## 本仓库不应包含的内容

- API key
- OAuth token
- cookie
- `auth.json`
- `secrets.env`
- `ccx/.config/config.json`
- 会话记录
- 日志
- 缓存
- SQLite 数据库
- macOS Keychain 内容
- 官方 Codex app 二进制
- `app.asar`

## API key 保存在哪里

配置脚本会把上游 DeepSeek API key 写入本机 `DEEPCODEX_HOME` 下的本地配置，用于本机转发服务。脚本不会在终端打印 key。

不要把整个 `DEEPCODEX_HOME` 目录打包发给别人。那个目录是运行态目录，不是源码仓库。

## 日志和会话

运行中的应用可能产生日志、会话和 SQLite 状态。这些内容可能包含提示词、文件路径、项目名或其他私人信息。

发布仓库只允许提交源码、模板和文档，不允许提交运行态数据。

## 分享排障信息时怎么脱敏

可以分享：

- 脚本版本
- `doctor` 的 OK/WARN/FAIL 标题
- base URL 的域名类型，例如“官方 DeepSeek”或“公司内网网关”
- macOS 版本

不要分享：

- API key 明文
- 完整 `auth.json`
- 完整 `secrets.env`
- 会话数据库
- 日志数据库
- 截图中可见的 token、cookie、私有 URL 或个人文件路径

## 发布前检查

```bash
scripts/audit-release.sh
git ls-files
```

如果 audit 失败，先修复再推送。
