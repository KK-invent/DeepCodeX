#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"
OUT_DIR="${OUT_DIR:-${ROOT}/dist/private}"

usage() {
  cat <<'EOF'
Usage:
  scripts/package-private-release.sh

Creates a private, user-installable DeepCodeX zip from an already verified
Deepcodex.app. The package is for private review/distribution only.

The package does not include Codex.app, app.asar sources from upstream, API keys,
or third-party runtime binaries. The DeepSeek bridge is the tracked Python
source in support/bin/deepcodex-deepseek-bridge.py.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --bundle-runtime) echo "[WARN] --bundle-runtime is deprecated; Python bridge is bundled as source." >&2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ ! -d "${DEEPCODEX_APP}" ]; then
  echo "[FAIL] Deepcodex.app not found: ${DEEPCODEX_APP}" >&2
  echo "普通用户请下载成品包；维护者请先构建并验证 Deepcodex.app。" >&2
  exit 2
fi

current_user="$(id -un 2>/dev/null || true)"
if [ -n "${current_user}" ] && rg -a -q -e "/Users/${current_user}" "${DEEPCODEX_APP}/Contents/Resources/app.asar"; then
  echo "[FAIL] app.asar still contains maintainer-specific paths." >&2
  echo "Run the current deepcodex-sync-upstream.py --stage/--apply first, then package the rebuilt app." >&2
  exit 2
fi

version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "${DEEPCODEX_APP}/Contents/Info.plist" 2>/dev/null || echo unknown)"
build="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "${DEEPCODEX_APP}/Contents/Info.plist" 2>/dev/null || echo 0)"
stamp="$(date '+%Y%m%d-%H%M%S')"
package_name="DeepCodeX-mac"
name="${package_name}"
work="$(mktemp -d)"
pkg="${work}/${name}"
mkdir -p "${pkg}/support" "${pkg}/runtime" "${OUT_DIR}"

cleanup() {
  rm -rf "${work}"
}
trap cleanup EXIT

echo "[package] copying app"
ditto --noqtn "${DEEPCODEX_APP}" "${pkg}/Deepcodex.app"

echo "[package] sanitizing app plist"
python3 - "${pkg}/Deepcodex.app/Contents/Info.plist" <<'PY'
import plistlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
info = plistlib.loads(path.read_bytes())
env = dict(info.get("LSEnvironment", {}))
for key in ("CCX_PROXY_ACCESS_KEY", "CODEX_HOME", "CODEX_ELECTRON_USER_DATA_PATH"):
    env.pop(key, None)
env.update({
    "CODEX_DEEPSEEK_APP": "1",
    "CODEX_SPARKLE_ENABLED": "false",
    "NO_PROXY": "127.0.0.1,localhost,::1",
    "no_proxy": "127.0.0.1,localhost,::1",
    "LANG": "zh_CN.UTF-8",
    "LC_ALL": "zh_CN.UTF-8",
    "LC_MESSAGES": "zh_CN.UTF-8",
    "LANGUAGE": "zh_CN:zh",
})
info["LSEnvironment"] = env
path.write_bytes(plistlib.dumps(info))
PY
codesign --force --deep --sign - "${pkg}/Deepcodex.app" >/dev/null

echo "[package] copying support files"
mkdir -p "${pkg}/support/bin" "${pkg}/support/config/launchagents" "${pkg}/support/docs" "${pkg}/support/scripts"
install -m 755 "${ROOT}/bin/"*.py "${pkg}/support/bin/"
install -m 755 "${ROOT}/bin/deepcodex-backup.sh" "${pkg}/support/bin/"
install -m 644 "${ROOT}/config/secrets.env.example" "${pkg}/support/config/secrets.env.example"
install -m 644 "${ROOT}/config/config.toml.example" "${pkg}/support/config/config.toml.example"
install -m 644 "${ROOT}/config/model-catalog.json" "${pkg}/support/config/model-catalog.json"
install -m 644 "${ROOT}/config/launchagents/"*.plist "${pkg}/support/config/launchagents/"
install -m 755 "${ROOT}/scripts/detect-install-mode.sh" "${pkg}/support/scripts/"
install -m 755 "${ROOT}/scripts/preflight-mac.sh" "${pkg}/support/scripts/"
install -m 644 "${ROOT}/README.zh-CN.md" "${pkg}/support/"
install -m 644 "${ROOT}/CHANGELOG.md" "${pkg}/support/"
mkdir -p "${pkg}/support/assets/brand"
install -m 644 "${ROOT}/assets/brand/"* "${pkg}/support/assets/brand/"
install -m 644 "${ROOT}/docs/INSTALL.zh-CN.md" "${pkg}/support/docs/"
install -m 644 "${ROOT}/docs/OFFLINE_QUICKSTART.zh-CN.md" "${pkg}/support/docs/"
install -m 644 "${ROOT}/docs/TROUBLESHOOTING.zh-CN.md" "${pkg}/support/docs/"
install -m 644 "${ROOT}/docs/PRIVACY.zh-CN.md" "${pkg}/support/docs/"

cat > "${pkg}/runtime/THIRD_PARTY_BINARIES.txt" <<'EOF'
This package does not include third-party runtime binaries.
DeepCodeX uses the tracked Python bridge in support/bin/deepcodex-deepseek-bridge.py.
EOF

cat > "${pkg}/Install-DeepCodeX.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"
CODEX_APP="${CODEX_APP:-/Applications/Codex.app}"
CODEX_DOWNLOAD_PAGE="${CODEX_DOWNLOAD_PAGE:-https://openai.com/codex/}"
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
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"

echo "== 安装 DeepCodeX =="
echo "安装脚本不会读取或上传你的 API key。"
echo "你需要准备 DeepSeek base URL 和 API key。"
echo ""
echo "== 环境检测 =="
if [ -x "${ROOT}/support/scripts/detect-install-mode.sh" ]; then
  CODEX_APP="${CODEX_APP}" DEEPCODEX_APP="${DEEPCODEX_APP}" CODEX_DOWNLOAD_PAGE="${CODEX_DOWNLOAD_PAGE}" "${ROOT}/support/scripts/detect-install-mode.sh" || true
else
  echo "[WARN] 未找到环境检测脚本，将继续安装。"
fi
echo ""
if [ ! -d "${CODEX_APP}" ]; then
  echo "[ACTION REQUIRED] 未检测到官方 Codex.app，DeepCodeX 安装暂不继续。"
  echo "请先从官方页面下载并安装 Codex:"
  echo "  ${CODEX_DOWNLOAD_PAGE}"
  echo "安装后确认 ${CODEX_APP} 存在，再重新运行 Install-DeepCodeX.command。"
  echo "如果这台 Mac 没有外网，请在有网机器从官方页面下载 Codex 安装包，再通过内网或 U 盘传入。"
  exit 2
fi
echo "[OK] official Codex app found: ${CODEX_APP}"
echo ""
echo "base URL 示例："
echo "  可直连官方 DeepSeek: https://api.deepseek.com"
echo "  无外网环境: 填你本机能访问的内网 DeepSeek/OpenAI-compatible 网关"
echo "  不要填写: 127.0.0.1:3100、代理地址、GitHub 地址、网页聊天地址"
echo ""

mkdir -p "${DEEPCODEX_HOME}/bin" "${DEEPCODEX_HOME}/logs" "${LAUNCH_AGENTS}"
install -m 755 "${ROOT}/support/bin/"*.py "${DEEPCODEX_HOME}/bin/"
install -m 755 "${ROOT}/support/bin/deepcodex-backup.sh" "${DEEPCODEX_HOME}/bin/deepcodex-backup.sh"
install -m 755 "${ROOT}/support/scripts/"*.sh "${DEEPCODEX_HOME}/bin/"
if [ ! -f "${DEEPCODEX_HOME}/secrets.env" ]; then
  install -m 600 "${ROOT}/support/config/secrets.env.example" "${DEEPCODEX_HOME}/secrets.env"
fi
if [ ! -f "${DEEPCODEX_HOME}/config.toml" ]; then
  install -m 644 "${ROOT}/support/config/config.toml.example" "${DEEPCODEX_HOME}/config.toml"
fi
if [ ! -f "${DEEPCODEX_HOME}/model-catalog.json" ]; then
  install -m 644 "${ROOT}/support/config/model-catalog.json" "${DEEPCODEX_HOME}/model-catalog.json"
fi

echo "[install] installing launchd services"
installed_plists=()
for tmpl in "${ROOT}/support/config/launchagents/"*.plist; do
  fname="$(basename "${tmpl}")"
  dest="${LAUNCH_AGENTS}/${fname}"
  sed -e "s|__DEEPCODEX_HOME__|${DEEPCODEX_HOME}|g" \
      -e "s|__LAUNCHD_DOMAIN__|${LAUNCHD_DOMAIN}|g" \
      "${tmpl}" > "${dest}"
  chmod 644 "${dest}"
  installed_plists+=("${dest}")
done

echo "[install] copying app to ${DEEPCODEX_APP}"
ditto --noqtn "${ROOT}/Deepcodex.app" "${DEEPCODEX_APP}"

echo "[config] 请填写 DeepSeek base URL 和 API key"
"${DEEPCODEX_HOME}/bin/deepcodex-configure-deepseek.py"

for label in "${LEGACY_LABELS[@]}"; do
  launchctl bootout "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
done
for plist in "${installed_plists[@]}"; do
  label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "${plist}")"
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
for plist in "${installed_plists[@]}"; do
  label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "${plist}")"
  launchctl bootstrap "gui/$(id -u)" "${plist}" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
done

echo "== 安装完成 =="
echo "可以打开：${DEEPCODEX_APP}"
echo "如需检查：${DEEPCODEX_HOME}/bin/deepcodex-doctor.py"
EOF
chmod +x "${pkg}/Install-DeepCodeX.command"

cat > "${pkg}/README-FIRST.zh-CN.txt" <<'EOF'
DeepCodeX Mac 私有成品包

第一步：双击 Install-DeepCodeX.command。
第二步：按提示填写 DeepSeek base URL 和 API key。

DeepCodeX 是统一安装包，不区分有 Codex 版和无 Codex 版。
安装器会先检测 /Applications/Codex.app；如果没有，会引导你去官方页面下载 Codex。

Codex 官方下载页面：
  https://openai.com/codex/

base URL 填你能访问的 DeepSeek/OpenAI-compatible 服务入口。
如果没有外网，请填写内网网关地址。
不要填写 127.0.0.1:3100；那是 DeepCodeX 内部地址。

安装脚本不会打印 API key。

如果 macOS 阻止打开，请先确认 .sha256 校验是 OK，再右键打开 Install-DeepCodeX.command。
仍被拦截时，只对校验通过的解压目录执行：
  xattr -dr com.apple.quarantine DeepCodeX-mac
EOF

cat > "${pkg}/PACKAGE-MANIFEST.txt" <<EOF
DeepCodeX private package
Asset name: ${package_name}.zip
Version: ${version}
Build: ${build}
Created: ${stamp}
Runtime: tracked Python bridge, no third-party runtime binary

Run: Install-DeepCodeX.command
EOF

echo "[package] auditing staged package"
"${ROOT}/scripts/audit-package.sh" "${pkg}"

zip_path="${OUT_DIR}/${name}.zip"
echo "[package] creating ${zip_path}"
rm -f "${zip_path}" "${zip_path}.sha256"
(cd "${work}" && /usr/bin/zip -qry "${zip_path}" "${name}")
(cd "$(dirname "${zip_path}")" && shasum -a 256 "$(basename "${zip_path}")" > "$(basename "${zip_path}").sha256")
"${ROOT}/scripts/audit-package.sh" "${zip_path}"

echo "Package: ${zip_path}"
echo "SHA256:  ${zip_path}.sha256"
