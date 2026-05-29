#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-${ROOT}/dist/private}"
REPO="${GITHUB_REPOSITORY:-}"
TAG=""
TITLE=""
NOTES_FILE="${ROOT}/docs/PRIVATE_RELEASE_NOTES.zh-CN.md"
INCLUDE_NO_CCX=1
INCLUDE_WITH_LOCAL_CCX=0
DRAFT=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  scripts/publish-private-release.sh --include-with-local-ccx [options]

Creates or updates a GitHub prerelease in the private repository and uploads
audited DeepCodeX package assets from dist/private.

Options:
  --repo OWNER/REPO              GitHub repository. Defaults to current gh repo.
  --tag TAG                      Release tag. Defaults to private-preview-YYYYMMDD-HHMMSS.
  --title TITLE                  Release title. Defaults to the tag.
  --notes-file FILE              Release notes markdown.
  --include-with-local-ccx       Upload the direct-use private package with bundled runtime.
  --no-no-ccx                    Do not upload the conservative no-ccx package.
  --draft                        Create the release as a draft.
  --dry-run                      Print the planned release and asset list, but do not upload.

The script refuses to run unless the GitHub repository is PRIVATE. Use
--include-with-local-ccx only after reviewing the private runtime boundary.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --tag) TAG="$2"; shift ;;
    --title) TITLE="$2"; shift ;;
    --notes-file) NOTES_FILE="$2"; shift ;;
    --include-with-local-ccx) INCLUDE_WITH_LOCAL_CCX=1 ;;
    --no-no-ccx) INCLUDE_NO_CCX=0 ;;
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
if [ "${INCLUDE_WITH_LOCAL_CCX}" -ne 1 ]; then
  echo "[FAIL] Refusing to publish a direct-use private release without --include-with-local-ccx." >&2
  echo "Use --no-no-ccx only to omit the conservative package, not the direct-use package." >&2
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
if [ "${INCLUDE_NO_CCX}" -eq 1 ]; then
  no_ccx="$(latest_matching 'DeepCodeX-private-no-ccx-*.zip')"
  if [ -z "${no_ccx}" ] || [ ! -f "${no_ccx}.sha256" ]; then
    echo "[FAIL] missing no-ccx package or checksum in ${OUT_DIR}" >&2
    exit 2
  fi
  assets+=("${no_ccx}" "${no_ccx}.sha256")
fi

with_ccx="$(latest_matching 'DeepCodeX-private-with-local-ccx-*.zip')"
if [ -z "${with_ccx}" ] || [ ! -f "${with_ccx}.sha256" ]; then
  echo "[FAIL] missing with-local-ccx package or checksum in ${OUT_DIR}" >&2
  exit 2
fi
assets+=("${with_ccx}" "${with_ccx}.sha256")

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
  echo "[release] existing release found; uploading assets with --clobber"
else
  gh release create "${TAG}" "${release_flags[@]}"
fi

gh release upload "${TAG}" "${assets[@]}" --repo "${REPO}" --clobber
gh release view "${TAG}" --repo "${REPO}" --json tagName,isDraft,isPrerelease,url,assets
