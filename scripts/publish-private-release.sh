#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-${ROOT}/dist/private}"
REPO="${GITHUB_REPOSITORY:-}"
TAG=""
TITLE=""
NOTES_FILE="${ROOT}/docs/PRIVATE_RELEASE_NOTES.zh-CN.md"
INCLUDE_RUNTIME_EXTERNAL=0
INCLUDE_RUNTIME_BUNDLED=0
DRAFT=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  scripts/publish-private-release.sh --include-runtime-bundled [options]

Creates or updates a GitHub prerelease in the private repository and uploads
audited DeepCodeX package assets from dist/private.

Options:
  --repo OWNER/REPO              GitHub repository. Defaults to current gh repo.
  --tag TAG                      Release tag. Defaults to private-preview-YYYYMMDD-HHMMSS.
  --title TITLE                  Release title. Defaults to the tag.
  --notes-file FILE              Release notes markdown.
  --include-runtime-bundled      Upload the package with bundled local runtime.
  --include-runtime-external     Also upload the conservative package without bundled runtime.
  --draft                        Create the release as a draft.
  --dry-run                      Print the planned release and asset list, but do not upload.

The script refuses to run unless the GitHub repository is PRIVATE. Use
--include-runtime-bundled only after reviewing the private runtime boundary.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --tag) TAG="$2"; shift ;;
    --title) TITLE="$2"; shift ;;
    --notes-file) NOTES_FILE="$2"; shift ;;
    --include-runtime-bundled) INCLUDE_RUNTIME_BUNDLED=1 ;;
    --include-runtime-external) INCLUDE_RUNTIME_EXTERNAL=1 ;;
    --draft) DRAFT=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
if [ -z "${TAG}" ]; then
  TAG="private-preview-$(date '+%Y%m%d-%H%M%S')"
fi
if [ -z "${TITLE}" ]; then
  TITLE="${TAG}"
fi
if [ "${INCLUDE_RUNTIME_BUNDLED}" -ne 1 ]; then
  echo "[FAIL] Refusing to publish a private release without --include-runtime-bundled." >&2
  echo "Use --include-runtime-external only when you also want to publish the package without bundled runtime." >&2
  exit 2
fi
if [ ! -f "${NOTES_FILE}" ]; then
  echo "[FAIL] release notes file missing: ${NOTES_FILE}" >&2
  exit 2
fi

visibility="$(gh repo view "${REPO}" --json visibility -q .visibility)"
if [ "${visibility}" != "PRIVATE" ]; then
  echo "[FAIL] Refusing to upload private binary packages to a non-private repo: ${REPO} (${visibility})" >&2
  exit 2
fi

latest_matching() {
  local pattern="$1"
  find "${OUT_DIR}" -maxdepth 1 -type f -name "${pattern}" -print | sort | tail -n 1
}

assets=()
if [ "${INCLUDE_RUNTIME_EXTERNAL}" -eq 1 ]; then
  external_pkg="$(latest_matching 'DeepCodeX-mac-no-runtime.zip')"
  if [ -z "${external_pkg}" ] || [ ! -f "${external_pkg}.sha256" ]; then
    echo "[FAIL] missing DeepCodeX-mac-no-runtime.zip or checksum in ${OUT_DIR}" >&2
    exit 2
  fi
  assets+=("${external_pkg}" "${external_pkg}.sha256")
fi

bundled_pkg="$(latest_matching 'DeepCodeX-mac.zip')"
if [ -z "${bundled_pkg}" ] || [ ! -f "${bundled_pkg}.sha256" ]; then
  echo "[FAIL] missing DeepCodeX-mac.zip or checksum in ${OUT_DIR}" >&2
  exit 2
fi
assets+=("${bundled_pkg}" "${bundled_pkg}.sha256")

echo "== Release preflight =="
"${ROOT}/scripts/audit-release.sh"
for asset in "${assets[@]}"; do
  case "${asset}" in
    *.zip) "${ROOT}/scripts/audit-package.sh" "${asset}" ;;
    *.sha256)
      current_user="$(id -un 2>/dev/null || true)"
      if [ -n "${current_user}" ] && rg -q -e "/Users/${current_user}" -e "${current_user}" "${asset}"; then
        echo "[FAIL] checksum leaks a maintainer path or username: ${asset}" >&2
        exit 1
      fi
      (cd "$(dirname "${asset}")" && shasum -a 256 -c "$(basename "${asset}")")
      ;;
  esac
done

target="$(git -C "${ROOT}" rev-parse HEAD)"
echo "Repository: ${REPO} (${visibility})"
echo "Tag:        ${TAG}"
echo "Target:     ${target}"
echo "Title:      ${TITLE}"
echo "Draft:      ${DRAFT}"
echo "Assets:"
printf '  %s\n' "${assets[@]}"

if [ "${DRY_RUN}" -eq 1 ]; then
  echo "Dry run only; no release was created."
  exit 0
fi

release_flags=(--repo "${REPO}" --title "${TITLE}" --notes-file "${NOTES_FILE}" --target "${target}" --prerelease)
if [ "${DRAFT}" -eq 1 ]; then
  release_flags+=(--draft)
fi

if gh release view "${TAG}" --repo "${REPO}" >/dev/null 2>&1; then
  echo "[release] existing release found; updating metadata and uploading assets with --clobber"
  edit_flags=(--repo "${REPO}" --title "${TITLE}" --notes-file "${NOTES_FILE}" --target "${target}" --prerelease)
  if [ "${DRAFT}" -eq 1 ]; then
    edit_flags+=(--draft)
  fi
  gh release edit "${TAG}" "${edit_flags[@]}"
else
  gh release create "${TAG}" "${release_flags[@]}"
fi

gh release upload "${TAG}" "${assets[@]}" --repo "${REPO}" --clobber
verify_flags=(--repo "${REPO}" --tag "${TAG}")
if [ "${INCLUDE_RUNTIME_EXTERNAL}" -eq 1 ]; then
  verify_flags+=(--allow-no-runtime)
fi
"${ROOT}/scripts/verify-release-assets.sh" "${verify_flags[@]}"
gh release view "${TAG}" --repo "${REPO}" --json tagName,isDraft,isPrerelease,url,assets
