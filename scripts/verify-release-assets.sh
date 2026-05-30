#!/usr/bin/env bash
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-}"
TAG=""
ALLOW_NO_RUNTIME=0

usage() {
  cat <<'EOF'
Usage:
  scripts/verify-release-assets.sh --tag TAG [--repo OWNER/REPO] [--allow-no-runtime]

Verifies that a GitHub release exposes only the expected concise DeepCodeX
asset names and that each .sha256 file references a bare zip filename.

Expected ordinary-user assets:
  DeepCodeX-mac.zip
  DeepCodeX-mac.zip.sha256

Options:
  --repo OWNER/REPO       GitHub repository. Defaults to current gh repo.
  --tag TAG               Release tag to verify.
  --allow-no-runtime      Also allow the maintainer-only no-runtime package.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --tag) TAG="$2"; shift ;;
    --allow-no-runtime) ALLOW_NO_RUNTIME=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
if [ -z "${TAG}" ]; then
  echo "[FAIL] --tag is required" >&2
  usage >&2
  exit 2
fi

tmp="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp}"
}
trap cleanup EXIT

retry() {
  local attempt=1
  local max_attempts=3
  until "$@"; do
    if [ "${attempt}" -ge "${max_attempts}" ]; then
      return 1
    fi
    echo "[retry] command failed; retrying $((attempt + 1))/${max_attempts}: $*" >&2
    sleep "${attempt}"
    attempt=$((attempt + 1))
  done
}

retry_stdout() {
  local output="$1"
  shift
  local attempt=1
  local max_attempts=3
  until "$@" > "${output}.tmp"; do
    rm -f "${output}.tmp"
    if [ "${attempt}" -ge "${max_attempts}" ]; then
      return 1
    fi
    echo "[retry] command failed; retrying $((attempt + 1))/${max_attempts}: $*" >&2
    sleep "${attempt}"
    attempt=$((attempt + 1))
  done
  mv "${output}.tmp" "${output}"
}

download_checksums() {
  rm -f "${checksums}"/*.sha256
  gh release download "${TAG}" --repo "${REPO}" --pattern '*.sha256' --dir "${checksums}" >/dev/null
}

expected="${tmp}/expected.txt"
actual="${tmp}/actual.txt"

cat > "${expected}" <<'EOF'
DeepCodeX-mac.zip
DeepCodeX-mac.zip.sha256
EOF

if [ "${ALLOW_NO_RUNTIME}" -eq 1 ]; then
  cat >> "${expected}" <<'EOF'
DeepCodeX-mac-no-runtime.zip
DeepCodeX-mac-no-runtime.zip.sha256
EOF
fi

LC_ALL=C sort -o "${expected}" "${expected}"
retry_stdout "${actual}.unsorted" gh release view "${TAG}" --repo "${REPO}" --json assets -q '.assets[].name'
LC_ALL=C sort "${actual}.unsorted" > "${actual}"

if ! cmp -s "${expected}" "${actual}"; then
  echo "[FAIL] release asset names do not match the expected public surface." >&2
  echo "Expected:" >&2
  sed 's/^/  /' "${expected}" >&2
  echo "Actual:" >&2
  sed 's/^/  /' "${actual}" >&2
  exit 1
fi

checksums="${tmp}/checksums"
mkdir -p "${checksums}"
retry download_checksums

for checksum in "${checksums}"/*.sha256; do
  [ -e "${checksum}" ] || continue
  base="$(basename "${checksum}" .sha256)"
  read -r digest filename extra < "${checksum}" || true
  if [ -n "${extra:-}" ] || ! printf '%s\n' "${digest:-}" | grep -Eq '^[0-9a-f]{64}$' || [ "${filename:-}" != "${base}" ]; then
    echo "[FAIL] checksum must contain exactly: <sha256>  ${base}" >&2
    echo "File: ${checksum}" >&2
    exit 1
  fi
  case "${filename}" in
    */*|*\\*)
      echo "[FAIL] checksum references a path instead of a bare filename: ${filename}" >&2
      exit 1
      ;;
  esac
done

echo "Release assets verified: ${REPO} ${TAG}"
