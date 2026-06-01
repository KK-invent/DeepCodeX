#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
# Regular Codex home whose conversations are imported into DeepCodeX so projects
# started in Codex can be continued here. Override with CODEX_SOURCE_HOME.
CODEX_SOURCE_HOME="${CODEX_SOURCE_HOME:-${HOME}/.codex}"
LAUNCHD_DOMAIN="${DEEPCODEX_LAUNCHD_DOMAIN:-com.deepcodex}"
LEGACY_CCX_LABEL="${DEEPCODEX_CCX_LABEL:-${LAUNCHD_DOMAIN}.ccx-deepseek}"
LEGACY_USER_DOMAIN="com.$(id -un)"
LEGACY_LABELS=(
  "${LEGACY_CCX_LABEL}"
  "com.deepcodex.ccx-deepseek"
  "${LEGACY_USER_DOMAIN}.ccx-deepseek"
  "${LEGACY_USER_DOMAIN}.deepcodex-image-strip"
  "${LEGACY_USER_DOMAIN}.deepseek-bridge"
)

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
installed_plists=()
installed_labels=()
for tmpl in "${ROOT}/config/launchagents/"*.plist; do
  fname="$(basename "${tmpl}")"
  dest="${LAUNCH_AGENTS}/${fname}"
  sed -e "s|__DEEPCODEX_HOME__|${DEEPCODEX_HOME}|g" \
      -e "s|__CODEX_SOURCE_HOME__|${CODEX_SOURCE_HOME}|g" \
      -e "s|__LAUNCHD_DOMAIN__|${LAUNCHD_DOMAIN}|g" \
      "${tmpl}" > "${dest}"
  chmod 644 "${dest}"
  label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "${dest}" 2>/dev/null || basename "${dest}" .plist)"
  installed_plists+=("${dest}")
  installed_labels+=("${label}")
  echo "Installed launchd plist: ${dest}"
done

echo "Stopping stale DeepCodeX services if present..."
for label in "${LEGACY_LABELS[@]}"; do
  launchctl bootout "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
done
for label in "${installed_labels[@]}"; do
  launchctl bootout "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
done
for label in "${LEGACY_USER_DOMAIN}.ccx-deepseek" "${LEGACY_USER_DOMAIN}.deepcodex-image-strip" "${LEGACY_USER_DOMAIN}.deepseek-bridge"; do
  legacy_plist="${LAUNCH_AGENTS}/${label}.plist"
  if [ -f "${legacy_plist}" ]; then
    mv "${legacy_plist}" "${legacy_plist}.disabled-python-bridge-$(date +%Y%m%d%H%M%S)"
  fi
done
pkill -f "${DEEPCODEX_HOME}/ccx/ccx" >/dev/null 2>&1 || true
pkill -f "${DEEPCODEX_HOME}/bin/deepcodex-deepseek-bridge.py" >/dev/null 2>&1 || true
pkill -f "${DEEPCODEX_HOME}/bin/deepcodex-image-strip-proxy.py" >/dev/null 2>&1 || true

echo "Bootstrapping DeepCodeX bridge services..."
for idx in "${!installed_plists[@]}"; do
  dest="${installed_plists[$idx]}"
  label="${installed_labels[$idx]}"
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
