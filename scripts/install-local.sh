#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
LAUNCHD_DOMAIN="${DEEPCODEX_LAUNCHD_DOMAIN:-com.deepcodex}"
LEGACY_CCX_LABEL="${DEEPCODEX_CCX_LABEL:-${LAUNCHD_DOMAIN}.ccx-deepseek}"

install -d "${DEEPCODEX_HOME}/bin" "${DEEPCODEX_HOME}/app-backups" "${DEEPCODEX_HOME}/cache-backups" "${DEEPCODEX_HOME}/logs"
install -m 755 "${ROOT}/bin/"*.py "${DEEPCODEX_HOME}/bin/"
install -m 755 "${ROOT}/bin/deepcodex-backup.sh" "${DEEPCODEX_HOME}/bin/deepcodex-backup.sh"

# Install config skeleton (only if not already present)
if [ ! -f "${DEEPCODEX_HOME}/secrets.env" ]; then
  install -m 600 "${ROOT}/config/secrets.env.example" "${DEEPCODEX_HOME}/secrets.env"
fi
if [ ! -f "${DEEPCODEX_HOME}/config.toml" ]; then
  install -m 644 "${ROOT}/config/config.toml.example" "${DEEPCODEX_HOME}/config.toml"
fi
if [ ! -f "${DEEPCODEX_HOME}/model-catalog.json" ]; then
  install -m 644 "${ROOT}/config/model-catalog.json" "${DEEPCODEX_HOME}/model-catalog.json"
fi

# Install launchd plist templates
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
install -d "${LAUNCH_AGENTS}"
LAUNCHD_DOMAIN="${DEEPCODEX_LAUNCHD_DOMAIN:-com.deepcodex}"
for tmpl in "${ROOT}/config/launchagents/"*.plist; do
  fname="$(basename "${tmpl}")"
  dest="${LAUNCH_AGENTS}/${fname}"
  sed -e "s|__DEEPCODEX_HOME__|${DEEPCODEX_HOME}|g" \
      -e "s|__LAUNCHD_DOMAIN__|${LAUNCHD_DOMAIN}|g" \
      "${tmpl}" > "${dest}"
  chmod 644 "${dest}"
  echo "Installed launchd plist: ${dest}"
done

echo "Stopping legacy ccx service if present..."
launchctl bootout "gui/$(id -u)/${LEGACY_CCX_LABEL}" >/dev/null 2>&1 || true

echo "Bootstrapping DeepCodeX bridge services..."
for tmpl in "${ROOT}/config/launchagents/"*.plist; do
  fname="$(basename "${tmpl}")"
  dest="${LAUNCH_AGENTS}/${fname}"
  label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "${dest}" 2>/dev/null || basename "${dest}" .plist)"
  launchctl bootout "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "${dest}" 2>/dev/null || true
  launchctl kickstart -k "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
  echo "  bootstrapped: ${label}"
done

echo "Installed DeepCodeX scripts to ${DEEPCODEX_HOME}"
echo ""
"${ROOT}/scripts/detect-install-mode.sh" || true
echo ""
echo "Next:"
echo "  1. 先配置 DeepSeek：${DEEPCODEX_HOME}/bin/deepcodex-configure-deepseek.py --restart-services"
echo "  2. 再构建 DeepCodeX：${DEEPCODEX_HOME}/bin/deepcodex-sync-upstream.py --stage"
echo "  3. 通过后应用：${DEEPCODEX_HOME}/bin/deepcodex-sync-upstream.py --apply"
echo "  4. 运行 doctor 验证：${DEEPCODEX_HOME}/bin/deepcodex-doctor.py"
