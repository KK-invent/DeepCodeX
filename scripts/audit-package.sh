#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: scripts/audit-package.sh <package-dir-or-zip>" >&2
  exit 2
fi

TARGET="$1"
WORK=""
cleanup() {
  if [ -n "${WORK}" ]; then
    rm -rf "${WORK}"
  fi
  return 0
}
trap cleanup EXIT

if [ -d "${TARGET}" ]; then
  ROOT="${TARGET}"
else
  WORK="$(mktemp -d)"
  /usr/bin/unzip -q "${TARGET}" -d "${WORK}"
  ROOT="${WORK}"
fi

echo "== Package audit: ${TARGET} =="

if find "${ROOT}" \( -name 'auth.json' -o -name 'secrets.env' -o -name '*.sqlite' -o -name '*.sqlite-*' -o -name '*.db' -o -name '*.log' -o -name 'session_index.jsonl' \) -print | grep -q .; then
  find "${ROOT}" \( -name 'auth.json' -o -name 'secrets.env' -o -name '*.sqlite' -o -name '*.sqlite-*' -o -name '*.db' -o -name '*.log' -o -name 'session_index.jsonl' \) -print
  echo "[FAIL] package contains banned runtime or secret-state filenames" >&2
  exit 1
fi

current_user="$(id -un 2>/dev/null || true)"
secret_patterns=(
  'CCX_PROXY_ACCESS_KEY[[:space:]]*=[[:space:]]*(ccx|dcx)[A-Za-z0-9_-]{12,}'
  'sk-[A-Za-z0-9_-]{20,}'
  'gh[pousr]_[A-Za-z0-9_]{20,}'
)
if [ -n "${current_user}" ]; then
  secret_patterns+=("/Users/${current_user}" "${current_user}")
fi
rg_args=()
for pattern in "${secret_patterns[@]}"; do
  rg_args+=("-e" "${pattern}")
done
if rg -n --hidden "${rg_args[@]}" "${ROOT}"; then
  echo "[FAIL] package contains a high-risk secret or maintainer path" >&2
  exit 1
fi

app="$(find "${ROOT}" -maxdepth 3 -type d -name 'Deepcodex.app' | head -n 1)"
if [ -z "${app}" ]; then
  echo "[FAIL] package does not contain Deepcodex.app" >&2
  exit 1
fi

required_paths=(
  "Install-DeepCodeX.command"
  "README-FIRST.zh-CN.txt"
  "support/README.zh-CN.md"
  "support/assets/brand/SOURCES.md"
  "support/assets/brand/deepcodex-icon.svg"
  "support/assets/brand/deepcodex-logo.svg"
  "support/assets/brand/deepcodex-logo.zh-CN.svg"
  "support/assets/brand/install-detection-flow.svg"
  "support/assets/brand/install-detection-flow.zh-CN.svg"
  "support/assets/brand/routing-architecture.svg"
  "support/assets/brand/routing-architecture.zh-CN.svg"
  "support/assets/brand/safety-scorecard.svg"
  "support/assets/brand/safety-scorecard.zh-CN.svg"
  "support/docs/INSTALL.zh-CN.md"
  "support/docs/OFFLINE_QUICKSTART.zh-CN.md"
  "support/docs/TROUBLESHOOTING.zh-CN.md"
  "support/docs/PRIVACY.zh-CN.md"
  "support/bin/deepcodex-deepseek-bridge.py"
  "support/config/config.toml.example"
  "support/config/model-catalog.json"
  "support/config/launchagents/com.deepcodex.deepseek-bridge.plist"
  "support/config/launchagents/com.deepcodex.deepcodex-image-strip.plist"
  "support/scripts/detect-install-mode.sh"
  "support/scripts/preflight-mac.sh"
  "runtime/THIRD_PARTY_BINARIES.txt"
)
package_root="$(dirname "${app}")"
for rel in "${required_paths[@]}"; do
  if [ ! -e "${package_root}/${rel}" ]; then
    echo "[FAIL] package is missing ${rel}" >&2
    exit 1
  fi
done

plist="${app}/Contents/Info.plist"
python3 - "${plist}" <<'PY'
import plistlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
info = plistlib.loads(path.read_bytes())
env = dict(info.get("LSEnvironment", {}))
bad = []
for key in ("CCX_PROXY_ACCESS_KEY", "CODEX_HOME", "CODEX_ELECTRON_USER_DATA_PATH"):
    if key in env:
        bad.append(key)
if bad:
    raise SystemExit("[FAIL] Info.plist contains maintainer/user-specific environment keys: " + ", ".join(bad))
print("[OK] Info.plist does not contain user-specific LSEnvironment keys")
PY

if [ -n "${current_user}" ] && rg -a -q -e "/Users/${current_user}" "${app}/Contents/Resources/app.asar"; then
  echo "[FAIL] app.asar contains hard-coded maintainer paths" >&2
  exit 1
fi

ccx_bin="$(find "${ROOT}" -path '*/runtime/ccx/ccx' -type f | head -n 1)"
if [ -n "${ccx_bin}" ]; then
  echo "[FAIL] package contains legacy runtime/ccx/ccx; Python bridge packages must not ship it" >&2
  exit 1
fi

echo "Package audit passed."
