#!/usr/bin/env bash
set -euo pipefail

CODEX_APP="${CODEX_APP:-/Applications/Codex.app}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"

has_codex=0
has_deepcodex=0
[ -d "${CODEX_APP}" ] && has_codex=1
[ -d "${DEEPCODEX_APP}" ] && has_deepcodex=1

echo "== DeepCodeX install mode detection =="
echo "Codex.app:     ${CODEX_APP}"
echo "Deepcodex.app: ${DEEPCODEX_APP}"

if [ "${has_deepcodex}" -eq 1 ] && [ "${has_codex}" -eq 1 ]; then
  cat <<EOF
[MODE] installed-with-upstream
当前电脑已经安装 DeepCodeX，也安装了 Codex。

建议下一步：
  1. 运行 doctor 检查 DeepCodeX 当前状态。
  2. 如果 doctor 提示 upstream-version-drift，维护者可运行 deepcodex-sync-upstream.py --stage。
EOF
elif [ "${has_deepcodex}" -eq 1 ]; then
  cat <<EOF
[MODE] app-user
当前电脑已经安装 DeepCodeX，但没有检测到 Codex。

这是普通用户成品包路径：
  1. 打开 DeepCodeX。
  2. 首次配置 DeepSeek base URL 和 API key。
  3. 不要运行源码重建脚本；没有 Codex 时无法从源码重建。
EOF
elif [ "${has_codex}" -eq 1 ]; then
  cat <<EOF
[MODE] codex-installed-no-deepcodex
当前电脑安装了 Codex，但还没有 DeepCodeX。

建议下一步：
  1. 普通用户可以继续安装 DeepCodeX 成品包。
  2. DeepCodeX 使用独立的 ~/.codex-deepseek 和 /Applications/Deepcodex.app，不覆盖原 Codex。
  3. 维护者如需从源码构建，再运行 deepcodex-sync-upstream.py --stage。
EOF
else
  cat <<EOF
[MODE] first-time-no-codex
当前电脑既没有 Codex，也没有 DeepCodeX。

这是完全新用户路径：
  1. 如果你是普通用户，请下载维护者提供的 DeepCodeX 成品包。
  2. 如果没有外网，请通过内网、U 盘或其他离线方式取得成品包。
  3. 安装后首次启动，填写 DeepSeek base URL 和 API key。
  4. 只有源码仓库时不能直接生成完整 DeepCodeX，因为仓库不分发官方 Codex 二进制。
EOF
fi
