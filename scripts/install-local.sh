#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"

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

# Bootstrap launchd services if DeepCodeX.app exists
if [ -d "/Applications/DeepCodeX.app" ] || [ -d "${HOME}/Applications/DeepCodeX.app" ]; then
  echo "DeepCodeX.app detected - bootstrapping launchd services..."
  for tmpl in "${ROOT}/config/launchagents/"*.plist; do
    fname="$(basename "${tmpl}")"
    dest="${LAUNCH_AGENTS}/${fname}"
    label="${LAUNCHD_DOMAIN}.${fname%.plist}"
    launchctl bootstrap "gui/$(id -u)" "${dest}" 2>/dev/null || true
    echo "  Bootstraped: ${label}"
  done
else
  echo "Skipping launchd bootstrap - no DeepCodeX.app found."
  echo "Run deepcodex-sync-upstream.py --apply to build it, then re-run this script."
fi

echo "Installed DeepCodeX scripts to ${DEEPCODEX_HOME}"
echo ""
"${ROOT}/scripts/detect-install-mode.sh" || true
echo ""
echo "Next:"
echo "  1. 打开 DeepCodeX.app -> '配置 DeepSeek...' 菜单，填写 base URL 和 API key"
echo "  2. 或命令行：${DEEPCODEX_HOME}/bin/deepcodex-configure-deepseek.py"
echo "  3. 运行 doctor 验证：${DEEPCODEX_HOME}/bin/deepcodex-doctor.py"
