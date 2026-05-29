#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: scripts/smoke-offline-package.sh <DeepCodeX-private-*.zip>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP="$1"
if [ ! -f "${ZIP}" ]; then
  echo "[FAIL] package not found: ${ZIP}" >&2
  exit 2
fi

WORK="$(mktemp -d)"
cleanup() {
  rm -rf "${WORK}"
}
trap cleanup EXIT

"${ROOT}/scripts/audit-package.sh" "${ZIP}"
/usr/bin/unzip -q "${ZIP}" -d "${WORK}"
PKG_ROOT="$(find "${WORK}" -maxdepth 1 -type d -name 'DeepCodeX-private-*' | head -n 1)"
if [ -z "${PKG_ROOT}" ]; then
  echo "[FAIL] package root not found after unzip" >&2
  exit 1
fi

INSTALLER="${PKG_ROOT}/Install-DeepCodeX.command"
APP="${PKG_ROOT}/Deepcodex.app"
CONFIGURE="${PKG_ROOT}/support/bin/deepcodex-configure-deepseek.py"
DETECT="${PKG_ROOT}/support/scripts/detect-install-mode.sh"

bash -n "${INSTALLER}"

detect_out="$(
  CODEX_APP="${WORK}/missing-Codex.app" \
  DEEPCODEX_APP="${WORK}/missing-Deepcodex.app" \
  "${DETECT}"
)"
printf '%s\n' "${detect_out}" | rg -q '\[MODE\] codex-required'

installer_out="$(
  HOME="${WORK}/installer-home" \
  CODEX_APP="${WORK}/missing-Codex.app" \
  DEEPCODEX_APP="${WORK}/installer-app/Deepcodex.app" \
  "${INSTALLER}" 2>&1 || true
)"
printf '%s\n' "${installer_out}" | rg -q '\[ACTION REQUIRED\].*Codex'
if [ -d "${WORK}/installer-app/Deepcodex.app" ]; then
  echo "[FAIL] installer copied Deepcodex.app even though Codex.app was missing" >&2
  exit 1
fi

case "$(basename "${ZIP}")" in
  *runtime-bundled*)
    test -x "${PKG_ROOT}/runtime/ccx/ccx"
    (cd "${PKG_ROOT}/runtime/ccx" && shasum -a 256 -c SHA256SUMS)
    ;;
  *runtime-external*)
    if [ -e "${PKG_ROOT}/runtime/ccx/ccx" ]; then
      echo "[FAIL] runtime-external package unexpectedly contains runtime/ccx/ccx" >&2
      exit 1
    fi
    ;;
esac

HOME_DIR="${WORK}/home"
DEEPCODEX_HOME="${HOME_DIR}/.codex-deepseek"
mkdir -p "${DEEPCODEX_HOME}"
config_out="${WORK}/configure.out"
smoke_key="smoke-test-key-123456"

printf '%s' "${smoke_key}" | \
  HOME="${HOME_DIR}" \
  DEEPCODEX_HOME="${DEEPCODEX_HOME}" \
  DEEPCODEX_APP="${APP}" \
  python3 "${CONFIGURE}" \
    --base-url "https://deepseek.example.internal" \
    --key-stdin \
    --no-confirm > "${config_out}"

if rg -q -e "${smoke_key}" "${config_out}"; then
  echo "[FAIL] configure output leaked API key" >&2
  exit 1
fi

HOME="${HOME_DIR}" \
DEEPCODEX_HOME="${DEEPCODEX_HOME}" \
DEEPCODEX_APP="${APP}" \
python3 "${CONFIGURE}" --check

echo "Offline package smoke passed: ${ZIP}"
