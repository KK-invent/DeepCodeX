#!/usr/bin/env bash
set -euo pipefail

CODEX_APP="${CODEX_APP:-/Applications/Codex.app}"
DEEPCODEX_APP="${DEEPCODEX_APP:-/Applications/Deepcodex.app}"
CODEX_DOWNLOAD_PAGE="${CODEX_DOWNLOAD_PAGE:-https://openai.com/codex/}"

usage() {
  cat <<'EOF'
Usage:
  scripts/detect-install-mode.sh [--selftest]

Detects whether this Mac has the official Codex app and/or DeepCodeX installed.
Set CODEX_APP and DEEPCODEX_APP to test non-default paths.
EOF
}

detect_mode() {
  local codex_app="$1"
  local deepcodex_app="$2"

  if [ -d "${deepcodex_app}" ] && [ -d "${codex_app}" ]; then
    echo "installed-with-upstream"
  elif [ -d "${deepcodex_app}" ]; then
    echo "codex-missing-existing-deepcodex"
  elif [ -d "${codex_app}" ]; then
    echo "ready-to-install"
  else
    echo "codex-required"
  fi
}

print_detection() {
  local mode
  mode="$(detect_mode "${CODEX_APP}" "${DEEPCODEX_APP}")"

  echo "== DeepCodeX install mode detection =="
  echo "Codex.app:     ${CODEX_APP}"
  echo "Deepcodex.app: ${DEEPCODEX_APP}"
  echo "Codex official download page: ${CODEX_DOWNLOAD_PAGE}"

  case "${mode}" in
    installed-with-upstream)
      cat <<EOF
[MODE] installed-with-upstream
当前电脑已经安装 DeepCodeX，也安装了 Codex。

建议下一步：
  1. 运行 doctor 检查 DeepCodeX 当前状态。
  2. 如果 doctor 提示 upstream-version-drift，维护者可运行 deepcodex-sync-upstream.py --stage。
EOF
      ;;
    codex-missing-existing-deepcodex)
      cat <<EOF
[MODE] codex-missing-existing-deepcodex
当前电脑已经安装 DeepCodeX，但没有检测到官方 Codex.app。

建议下一步：
  1. 先从官方页面下载并安装 Codex: ${CODEX_DOWNLOAD_PAGE}
  2. 把 Codex.app 放到 /Applications/Codex.app 后，再重新运行 DeepCodeX 安装器或 doctor。
  3. 如果这台 Mac 没有外网，请在有网机器从官方页面下载 Codex 安装包，再通过内网或 U 盘传入。
EOF
      ;;
    ready-to-install)
      cat <<EOF
[MODE] ready-to-install
当前电脑安装了 Codex，但还没有 DeepCodeX。

建议下一步：
  1. 继续运行 DeepCodeX 统一安装包。
  2. DeepCodeX 使用独立的 ~/.codex-deepseek 和 /Applications/Deepcodex.app，不覆盖原 Codex。
  3. 安装后填写 DeepSeek base URL 和 API key。
EOF
      ;;
    codex-required)
      cat <<EOF
[MODE] codex-required
当前电脑既没有 Codex，也没有 DeepCodeX。

DeepCodeX 统一安装包需要先检测到官方 Codex.app：
  1. 从官方页面下载并安装 Codex: ${CODEX_DOWNLOAD_PAGE}
  2. 确认 /Applications/Codex.app 存在。
  3. 然后重新运行 Install-DeepCodeX.command。
  4. 如果这台 Mac 没有外网，请在有网机器从官方页面下载 Codex 安装包，再通过内网或 U 盘传入。
EOF
      ;;
    *)
      echo "[FAIL] unknown install mode: ${mode}" >&2
      return 1
      ;;
  esac
}

selftest() {
  local work
  SELFTEST_WORK="$(mktemp -d)"
  trap 'rm -rf "${SELFTEST_WORK:-}"' EXIT
  work="${SELFTEST_WORK}"

  check_case() {
    local name="$1"
    local expected="$2"
    local make_codex="$3"
    local make_deepcodex="$4"
    local case_dir="${work}/${name}"
    local codex_app="${case_dir}/Codex.app"
    local deepcodex_app="${case_dir}/Deepcodex.app"
    local actual

    mkdir -p "${case_dir}"
    [ "${make_codex}" -eq 1 ] && mkdir -p "${codex_app}"
    [ "${make_deepcodex}" -eq 1 ] && mkdir -p "${deepcodex_app}"

    actual="$(detect_mode "${codex_app}" "${deepcodex_app}")"
    if [ "${actual}" != "${expected}" ]; then
      echo "[FAIL] ${name}: expected ${expected}, got ${actual}" >&2
      exit 1
    fi
  }

  check_case "nothing-installed" "codex-required" 0 0
  check_case "codex-only" "ready-to-install" 1 0
  check_case "deepcodex-only" "codex-missing-existing-deepcodex" 0 1
  check_case "both-installed" "installed-with-upstream" 1 1

  echo "install mode detection selftest OK"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --selftest) selftest; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

print_detection
