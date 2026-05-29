#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"

install -d "${DEEPCODEX_HOME}/bin" "${DEEPCODEX_HOME}/app-backups" "${DEEPCODEX_HOME}/cache-backups"
install -m 755 "${ROOT}/bin/"*.py "${DEEPCODEX_HOME}/bin/"
install -m 755 "${ROOT}/bin/deepcodex-backup.sh" "${DEEPCODEX_HOME}/bin/deepcodex-backup.sh"

if [ ! -f "${DEEPCODEX_HOME}/secrets.env" ]; then
  install -m 600 "${ROOT}/config/secrets.env.example" "${DEEPCODEX_HOME}/secrets.env"
fi

echo "Installed DeepCodeX scripts to ${DEEPCODEX_HOME}"
echo "Next: ${DEEPCODEX_HOME}/bin/deepcodex-configure-deepseek.py"
