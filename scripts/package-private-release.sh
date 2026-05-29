#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"
OUT_DIR="${OUT_DIR:-${ROOT}/dist/private}"
INCLUDE_LOCAL_CCX=0

usage() {
  cat <<'EOF'
Usage:
  scripts/package-private-release.sh [--include-local-ccx]

Creates a private, user-installable DeepCodeX zip from an already verified
Deepcodex.app. The package is for private review/distribution only.

By default the package excludes the local ccx binary. Use --include-local-ccx
only after reviewing redistribution rights for that binary.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --include-local-ccx) INCLUDE_LOCAL_CCX=1 ;;
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
runtime_suffix="no-ccx"
if [ "${INCLUDE_LOCAL_CCX}" -eq 1 ]; then
  runtime_suffix="with-local-ccx"
fi
name="DeepCodeX-private-${runtime_suffix}-${version}-${build}-${stamp}"
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
mkdir -p "${pkg}/support/bin" "${pkg}/support/config" "${pkg}/support/docs" "${pkg}/support/scripts"
install -m 755 "${ROOT}/bin/"*.py "${pkg}/support/bin/"
install -m 755 "${ROOT}/bin/deepcodex-backup.sh" "${pkg}/support/bin/"
install -m 644 "${ROOT}/config/secrets.env.example" "${pkg}/support/config/secrets.env.example"
install -m 755 "${ROOT}/scripts/detect-install-mode.sh" "${pkg}/support/scripts/"
install -m 755 "${ROOT}/scripts/preflight-mac.sh" "${pkg}/support/scripts/"
install -m 644 "${ROOT}/README.zh-CN.md" "${pkg}/support/"
install -m 644 "${ROOT}/docs/INSTALL.zh-CN.md" "${pkg}/support/docs/"
install -m 644 "${ROOT}/docs/OFFLINE_QUICKSTART.zh-CN.md" "${pkg}/support/docs/"
install -m 644 "${ROOT}/docs/TROUBLESHOOTING.zh-CN.md" "${pkg}/support/docs/"
install -m 644 "${ROOT}/docs/PRIVACY.zh-CN.md" "${pkg}/support/docs/"

if [ "${INCLUDE_LOCAL_CCX}" -eq 1 ]; then
  if [ ! -x "${DEEPCODEX_HOME}/ccx/ccx" ]; then
    echo "[FAIL] --include-local-ccx requested, but ${DEEPCODEX_HOME}/ccx/ccx is missing" >&2
    exit 2
  fi
  mkdir -p "${pkg}/runtime/ccx"
  install -m 755 "${DEEPCODEX_HOME}/ccx/ccx" "${pkg}/runtime/ccx/ccx"
  (cd "${pkg}/runtime/ccx" && shasum -a 256 ccx > SHA256SUMS)
  cat > "${pkg}/runtime/THIRD_PARTY_BINARIES.txt" <<'EOF'
This private package includes a local ccx binary supplied by the maintainer.
Review redistribution rights before making this package public.
EOF
else
  cat > "${pkg}/runtime/THIRD_PARTY_BINARIES.txt" <<'EOF'
This private package does not include the ccx runtime binary.
DeepCodeX can be installed, but the DeepSeek route will not work until a
compatible local ccx runtime is installed at $DEEPCODEX_HOME/ccx/ccx.
EOF
fi

cat > "${pkg}/Install-DeepCodeX.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"
LAUNCHD_DOMAIN="${DEEPCODEX_LAUNCHD_DOMAIN:-com.deepcodex}"
CCX_LABEL="${DEEPCODEX_CCX_LABEL:-${LAUNCHD_DOMAIN}.ccx-deepseek}"
IMAGE_STRIP_LABEL="${DEEPCODEX_IMAGE_STRIP_LABEL:-${LAUNCHD_DOMAIN}.deepcodex-image-strip}"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"

echo "== 安装 DeepCodeX =="
echo "安装脚本不会读取或上传你的 API key。"
echo "你需要准备 DeepSeek base URL 和 API key。"
echo ""
echo "== 环境检测 =="
if [ -x "${ROOT}/support/scripts/detect-install-mode.sh" ]; then
  CODEX_APP="${CODEX_APP:-/Applications/Codex.app}" DEEPCODEX_APP="${DEEPCODEX_APP}" "${ROOT}/support/scripts/detect-install-mode.sh" || true
else
  echo "[WARN] 未找到环境检测脚本，将继续安装。"
fi
echo ""
echo "base URL 示例："
echo "  可直连官方 DeepSeek: https://api.deepseek.com"
echo "  无外网环境: 填你本机能访问的内网 DeepSeek/OpenAI-compatible 网关"
echo "  不要填写: 127.0.0.1:3100、代理地址、GitHub 地址、网页聊天地址"
echo ""

mkdir -p "${DEEPCODEX_HOME}/bin" "${DEEPCODEX_HOME}/logs" "${DEEPCODEX_HOME}/ccx" "${LAUNCH_AGENTS}"
install -m 755 "${ROOT}/support/bin/"*.py "${DEEPCODEX_HOME}/bin/"
install -m 755 "${ROOT}/support/bin/deepcodex-backup.sh" "${DEEPCODEX_HOME}/bin/deepcodex-backup.sh"
install -m 755 "${ROOT}/support/scripts/"*.sh "${DEEPCODEX_HOME}/bin/"
if [ ! -f "${DEEPCODEX_HOME}/secrets.env" ]; then
  install -m 600 "${ROOT}/support/config/secrets.env.example" "${DEEPCODEX_HOME}/secrets.env"
fi

RUNTIME_READY=0
if [ -x "${ROOT}/runtime/ccx/ccx" ]; then
  if [ -f "${ROOT}/runtime/ccx/SHA256SUMS" ]; then
    (cd "${ROOT}/runtime/ccx" && shasum -a 256 -c SHA256SUMS)
  fi
  install -m 755 "${ROOT}/runtime/ccx/ccx" "${DEEPCODEX_HOME}/ccx/ccx"
  RUNTIME_READY=1
  echo "[OK] bundled ccx runtime installed"
elif [ -x "${DEEPCODEX_HOME}/ccx/ccx" ]; then
  RUNTIME_READY=1
  echo "[OK] existing ccx runtime found: ${DEEPCODEX_HOME}/ccx/ccx"
else
  echo "[WARN] package does not contain ccx runtime; DeepSeek route needs ${DEEPCODEX_HOME}/ccx/ccx"
  echo "[WARN] ordinary first-time users should ask for a with-local-ccx package"
fi

echo "[install] copying app to ${DEEPCODEX_APP}"
ditto --noqtn "${ROOT}/Deepcodex.app" "${DEEPCODEX_APP}"

if [ "${RUNTIME_READY}" -eq 1 ]; then
  cat > "${LAUNCH_AGENTS}/${CCX_LABEL}.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${CCX_LABEL}</string>
  <key>ProgramArguments</key><array><string>${DEEPCODEX_HOME}/ccx/ccx</string></array>
  <key>WorkingDirectory</key><string>${DEEPCODEX_HOME}/ccx</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${DEEPCODEX_HOME}/logs/ccx.out.log</string>
  <key>StandardErrorPath</key><string>${DEEPCODEX_HOME}/logs/ccx.err.log</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict></plist>
PLIST

  cat > "${LAUNCH_AGENTS}/${IMAGE_STRIP_LABEL}.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${IMAGE_STRIP_LABEL}</string>
  <key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>${DEEPCODEX_HOME}/bin/deepcodex-image-strip-proxy.py</string></array>
  <key>WorkingDirectory</key><string>${DEEPCODEX_HOME}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${DEEPCODEX_HOME}/logs/image-strip.out.log</string>
  <key>StandardErrorPath</key><string>${DEEPCODEX_HOME}/logs/image-strip.err.log</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>LISTEN_HOST</key><string>127.0.0.1</string>
    <key>LISTEN_PORT</key><string>3100</string>
    <key>UPSTREAM_HOST</key><string>127.0.0.1</string>
    <key>UPSTREAM_PORT</key><string>3000</string>
  </dict>
</dict></plist>
PLIST
else
  echo "[WARN] runtime is missing; launchd service files were not written"
fi

echo "[config] 请填写 DeepSeek base URL 和 API key"
"${DEEPCODEX_HOME}/bin/deepcodex-configure-deepseek.py"

if [ "${RUNTIME_READY}" -eq 1 ]; then
  for label in "${CCX_LABEL}" "${IMAGE_STRIP_LABEL}"; do
    plist="${LAUNCH_AGENTS}/${label}.plist"
    launchctl bootout "gui/$(id -u)" "${plist}" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "${plist}" >/dev/null 2>&1 || true
    launchctl kickstart -k "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
  done
else
  echo "[WARN] DeepCodeX installed, but runtime is missing; model requests will not work yet"
fi

echo "== 安装完成 =="
echo "可以打开：${DEEPCODEX_APP}"
echo "如需检查：${DEEPCODEX_HOME}/bin/deepcodex-doctor.py"
EOF
chmod +x "${pkg}/Install-DeepCodeX.command"

cat > "${pkg}/README-FIRST.zh-CN.txt" <<'EOF'
DeepCodeX 私有成品包

第一步：双击 Install-DeepCodeX.command。
第二步：按提示填写 DeepSeek base URL 和 API key。

完全没装 Codex 的新用户，建议使用文件名包含 with-local-ccx 的包。
如果文件名包含 no-ccx，说明包内不带 runtime，普通新用户还不能直接发起模型请求。

base URL 填你能访问的 DeepSeek/OpenAI-compatible 服务入口。
如果没有外网，请填写内网网关地址。
不要填写 127.0.0.1:3100；那是 DeepCodeX 内部地址。

安装脚本不会打印 API key。
EOF

cat > "${pkg}/PACKAGE-MANIFEST.txt" <<EOF
DeepCodeX private package
Version: ${version}
Build: ${build}
Created: ${stamp}
Includes local ccx: ${INCLUDE_LOCAL_CCX}

Run: Install-DeepCodeX.command
EOF

echo "[package] auditing staged package"
"${ROOT}/scripts/audit-package.sh" "${pkg}"

zip_path="${OUT_DIR}/${name}.zip"
echo "[package] creating ${zip_path}"
(cd "${work}" && /usr/bin/zip -qry "${zip_path}" "${name}")
shasum -a 256 "${zip_path}" > "${zip_path}.sha256"
"${ROOT}/scripts/audit-package.sh" "${zip_path}"

echo "Package: ${zip_path}"
echo "SHA256:  ${zip_path}.sha256"
