#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="${GITHUB_REPOSITORY:-}"
VERSION_FILE="${ROOT}/VERSION"
NOTES_FILE="${ROOT}/docs/PUBLIC_SOURCE_RELEASE_NOTES.md"
TAG=""
TITLE=""
DRY_RUN=0
SKIP_PUBLIC_CHECK=0

usage() {
  cat <<'EOF'
Usage:
  scripts/publish-public-source-release.sh [--repo OWNER/REPO] [--tag vX.Y.Z] [--dry-run] [--skip-public-check]

Creates a source-only GitHub Release for the public source version. It never
uploads binary assets. GitHub will still show the standard source archive links.

Options:
  --repo OWNER/REPO      GitHub repository. Defaults to current gh repo.
  --tag vX.Y.Z           Release tag. Defaults to v$(cat VERSION).
  --dry-run              Print the planned tag/release actions only.
  --skip-public-check    Allow dry-run planning while the repository is still private.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --tag) TAG="$2"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    --skip-public-check) SKIP_PUBLIC_CHECK=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
if [ ! -f "${VERSION_FILE}" ]; then
  echo "[FAIL] missing VERSION" >&2
  exit 2
fi
version="$(cat "${VERSION_FILE}")"
if ! printf '%s\n' "${version}" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "[FAIL] VERSION must contain semver like 0.1.0: ${version}" >&2
  exit 2
fi
if [ -z "${TAG}" ]; then
  TAG="v${version}"
fi
if [ "${TAG}" != "v${version}" ]; then
  echo "[FAIL] tag ${TAG} does not match VERSION ${version}" >&2
  exit 2
fi
TITLE="DeepCodeX ${TAG} public source release"
if [ ! -s "${NOTES_FILE}" ]; then
  echo "[FAIL] missing public source release notes: ${NOTES_FILE}" >&2
  exit 2
fi

visibility="$(gh repo view "${REPO}" --json visibility -q .visibility)"
if [ "${visibility}" != "PUBLIC" ]; then
  if [ "${SKIP_PUBLIC_CHECK}" -eq 1 ] && [ "${DRY_RUN}" -eq 1 ]; then
    echo "[WARN] repository is ${visibility}; continuing because this is a dry-run plan."
  else
    echo "[FAIL] refusing to publish a public source release while repo is ${visibility}" >&2
    echo "Run scripts/prepare-public-source-release.sh first, then make the repo public." >&2
    echo "Use --dry-run --skip-public-check only for private preflight planning." >&2
    exit 2
  fi
fi

echo "== Source release preflight =="
"${ROOT}/scripts/audit-release.sh"
if ! "${ROOT}/scripts/verify-github-public-metadata.sh" --repo "${REPO}"; then
  exit 1
fi

if ! git -C "${ROOT}" diff --quiet || ! git -C "${ROOT}" diff --cached --quiet; then
  echo "[FAIL] git worktree is dirty; commit or discard changes before release" >&2
  exit 1
fi

target="$(git -C "${ROOT}" rev-parse HEAD)"
echo "Repository: ${REPO} (${visibility})"
echo "Tag:        ${TAG}"
echo "Target:     ${target}"
echo "Title:      ${TITLE}"
echo "Notes:      ${NOTES_FILE}"
echo "Assets:     none"

if [ "${DRY_RUN}" -eq 1 ]; then
  echo "Dry run only; no tag or release was created."
  exit 0
fi

if ! git -C "${ROOT}" rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  git -C "${ROOT}" tag -a "${TAG}" -m "${TAG}"
fi
git -C "${ROOT}" push origin "${TAG}"

if gh release view "${TAG}" --repo "${REPO}" >/dev/null 2>&1; then
  gh release edit "${TAG}" --repo "${REPO}" --title "${TITLE}" --notes-file "${NOTES_FILE}" --target "${target}" --latest
else
  gh release create "${TAG}" --repo "${REPO}" --title "${TITLE}" --notes-file "${NOTES_FILE}" --target "${target}" --latest
fi

"${ROOT}/scripts/verify-public-source-release.sh" --repo "${REPO}" --tag "${TAG}"
