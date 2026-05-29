#!/usr/bin/env bash
set -euo pipefail

CODEX_APP="${CODEX_APP:-/Applications/Codex.app}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"
CODEX_DOWNLOAD_PAGE="${CODEX_DOWNLOAD_PAGE:-https://openai.com/codex/}"

has_codex=0
has_deepcodex=0
[ -d "${CODEX_APP}" ] && has_codex=1
[ -d "${DEEPCODEX_APP}" ] && has_deepcodex=1

echo "== DeepCodeX install mode detection =="
echo "Codex.app:     ${CODEX_APP}"
echo "Deepcodex.app: ${DEEPCODEX_APP}"
echo "Codex official download page: ${CODEX_DOWNLOAD_PAGE}"

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
[MODE] codex-missing-existing-deepcodex
当前电脑已经安装 DeepCodeX，但没有检测到官方 Codex.app。

建议下一步：
  1. 先从官方页面下载并安装 Codex: ${CODEX_DOWNLOAD_PAGE}
  2. 把 Codex.app 放到 /Applications/Codex.app 后，再重新运行 DeepCodeX 安装器或 doctor。
  3. 如果这台 Mac 没有外网，请在有网机器从官方页面下载 Codex 安装包，再通过内网或 U 盘传入。
EOF
elif [ "${has_codex}" -eq 1 ]; then
  cat <<EOF
[MODE] ready-to-install
当前电脑安装了 Codex，但还没有 DeepCodeX。

建议下一步：
  1. 继续运行 DeepCodeX 统一安装包。
  2. DeepCodeX 使用独立的 ~/.codex-deepseek 和 /Applications/Deepcodex.app，不覆盖原 Codex。
  3. 安装后填写 DeepSeek base URL 和 API key。
EOF
else
  cat <<EOF
[MODE] codex-required
当前电脑既没有 Codex，也没有 DeepCodeX。

DeepCodeX 统一安装包需要先检测到官方 Codex.app：
  1. 从官方页面下载并安装 Codex: ${CODEX_DOWNLOAD_PAGE}
  2. 确认 /Applications/Codex.app 存在。
  3. 然后重新运行 Install-DeepCodeX.command。
  4. 如果这台 Mac 没有外网，请在有网机器从官方页面下载 Codex 安装包，再通过内网或 U 盘传入。
EOF
fi
