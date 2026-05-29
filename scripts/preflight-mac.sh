#!/usr/bin/env bash
set -euo pipefail

DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
CODEX_APP="${CODEX_APP:-/Applications/Codex.app}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"
SECRETS_FILE="${DEEPCODEX_HOME}/secrets.env"

warn() { printf '[WARN] %s\n' "$*"; }
ok() { printf '[OK] %s\n' "$*"; }
fail_note() { printf '[INFO] %s\n' "$*"; }

echo "== DeepCodeX macOS preflight =="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "${SCRIPT_DIR}/detect-install-mode.sh" ]; then
  "${SCRIPT_DIR}/detect-install-mode.sh"
  echo ""
fi

if [ "$(uname -s)" = "Darwin" ]; then
  ok "macOS detected"
else
  warn "This toolkit currently targets macOS."
fi

if command -v python3 >/dev/null 2>&1; then
  ok "python3: $(python3 --version 2>&1)"
else
  warn "python3 not found. Install Python 3.10+ before using maintainer scripts."
fi

if [ -d "${CODEX_APP}" ]; then
  ok "Codex.app found: ${CODEX_APP}"
else
  warn "Codex.app not found: ${CODEX_APP}"
  fail_note "普通用户：请使用维护者提供的 DeepCodeX 成品包。"
  fail_note "维护者：源码仓库不包含官方 Codex 二进制；需要先安装官方 Codex desktop app，或在合规允许的私有环境准备成品包。"
fi

if [ -d "${DEEPCODEX_APP}" ]; then
  ok "Deepcodex.app found: ${DEEPCODEX_APP}"
else
  warn "Deepcodex.app not found: ${DEEPCODEX_APP}"
  fail_note "如果你只有源码仓库，需要先由维护者用 deepcodex-sync-upstream.py --stage/--apply 构建。"
fi

if [ -n "${HTTP_PROXY:-}${HTTPS_PROXY:-}${ALL_PROXY:-}${http_proxy:-}${https_proxy:-}${all_proxy:-}" ]; then
  warn "Proxy environment variables are set. DeepCodeX does not require a proxy for local 127.0.0.1 routing."
else
  ok "No proxy environment variables detected"
fi

case ",${NO_PROXY:-${no_proxy:-}}," in
  *127.0.0.1*|*localhost*|*"::1"*) ok "NO_PROXY/no_proxy includes a local loopback entry" ;;
  *) warn "Set NO_PROXY/no_proxy to include 127.0.0.1,localhost,::1 to protect local shim traffic" ;;
esac

BASE_URL="${DEEPSEEK_BASE_URL:-${DEEPCODEX_DEEPSEEK_BASE_URL:-}}"
if [ -z "${BASE_URL}" ] && [ -f "${SECRETS_FILE}" ]; then
  BASE_URL="$(awk -F= '/^DEEPSEEK_BASE_URL=/{print $2; exit}' "${SECRETS_FILE}")"
fi

if [ -z "${BASE_URL}" ]; then
  warn "DeepSeek base URL not configured yet"
  fail_note "能直连官方 DeepSeek 时填：https://api.deepseek.com"
  fail_note "无外网但有内网模型服务时，填内网 DeepSeek/OpenAI-compatible 网关。"
  fail_note "不要填写 127.0.0.1:3100；那是 DeepCodeX 内部 shim 地址。"
else
  python3 - "${BASE_URL}" <<'PY'
import sys
from urllib.parse import urlparse

url = sys.argv[1].strip().rstrip("/")
parsed = urlparse(url)
if parsed.scheme in {"http", "https"} and parsed.netloc:
    print(f"[OK] DeepSeek base URL shape looks valid: {url}")
else:
    print(f"[WARN] DeepSeek base URL is not an http(s) URL: {url}")
PY
fi

if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  ok "DEEPSEEK_API_KEY is present in environment (value not printed)"
elif [ -f "${SECRETS_FILE}" ] && grep -q '^CCX_PROXY_ACCESS_KEY=.' "${SECRETS_FILE}"; then
  ok "Local proxy key exists in secrets.env (value not printed)"
else
  warn "No API key signal found yet. Run: ${DEEPCODEX_HOME}/bin/deepcodex-configure-deepseek.py"
fi

echo "== Next =="
echo "普通用户：打开 DeepCodeX 成品包，填写 DeepSeek base URL 和 API key。"
echo "维护者：运行 ${DEEPCODEX_HOME}/bin/deepcodex-sync-upstream.py --stage。"
