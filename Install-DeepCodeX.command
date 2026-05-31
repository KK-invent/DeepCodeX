#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
CODEX_APP="${CODEX_APP:-/Applications/Codex.app}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"
CODEX_DOWNLOAD_PAGE="${CODEX_DOWNLOAD_PAGE:-https://openai.com/codex/}"

echo "== DeepCodeX 小白安装器 =="
echo "这个安装器只使用本仓库的开源脚本，不包含官方 Codex.app。"
echo "你需要准备：官方 Codex、DeepSeek base URL、DeepSeek API key。"
echo ""

if [ ! -x "${ROOT}/scripts/install-local.sh" ] || [ ! -x "${ROOT}/bin/deepcodex-sync-upstream.py" ]; then
  echo "[FAIL] 当前目录不完整。请先完整解压 GitHub 下载的 DeepCodeX 源码 zip，再双击本文件。"
  exit 2
fi

echo "== 第 1 步：检测 Codex =="
if [ -x "${ROOT}/scripts/detect-install-mode.sh" ]; then
  CODEX_APP="${CODEX_APP}" DEEPCODEX_APP="${DEEPCODEX_APP}" CODEX_DOWNLOAD_PAGE="${CODEX_DOWNLOAD_PAGE}" \
    "${ROOT}/scripts/detect-install-mode.sh" || true
fi
echo ""

if [ ! -d "${CODEX_APP}" ]; then
  echo "[ACTION REQUIRED] 未检测到官方 Codex.app，DeepCodeX 暂不继续安装。"
  echo "请先下载并安装官方 Codex："
  echo "  ${CODEX_DOWNLOAD_PAGE}"
  echo ""
  echo "安装完成后确认这个路径存在："
  echo "  ${CODEX_APP}"
  echo ""
  echo "然后重新双击 Install-DeepCodeX.command。"
  if [ "${DEEPCODEX_NO_OPEN:-0}" != "1" ] && command -v open >/dev/null 2>&1; then
    open "${CODEX_DOWNLOAD_PAGE}" >/dev/null 2>&1 || true
  fi
  exit 2
fi
echo "[OK] 已检测到官方 Codex：${CODEX_APP}"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "[FAIL] 未检测到 python3。请先安装 Python 3.10+，再重新运行本安装器。"
  exit 2
fi

echo "== 第 2 步：安装本地维护工具和 bridge 服务 =="
"${ROOT}/scripts/install-local.sh"
echo ""

echo "== 第 3 步：填写 DeepSeek 配置 =="
echo "base URL 能直连官方 DeepSeek 时直接回车即可使用默认值：https://api.deepseek.com"
echo "不要填写 127.0.0.1:3100、代理地址、GitHub 地址或网页聊天地址。"
"${DEEPCODEX_HOME}/bin/deepcodex-configure-deepseek.py" --restart-services
echo ""

echo "== 第 4 步：从本机 Codex 构建 DeepCodeX =="
echo "这一步会创建 /Applications/Deepcodex.app，不会覆盖 /Applications/Codex.app。"
"${DEEPCODEX_HOME}/bin/deepcodex-sync-upstream.py" --apply
echo ""

echo "== 第 5 步：检查安装状态 =="
"${DEEPCODEX_HOME}/bin/deepcodex-doctor.py"
echo ""

echo "== 完成 =="
echo "可以打开：${DEEPCODEX_APP}"
if command -v open >/dev/null 2>&1; then
  open "${DEEPCODEX_APP}" >/dev/null 2>&1 || true
fi
