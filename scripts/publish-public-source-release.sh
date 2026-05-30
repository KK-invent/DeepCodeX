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
PRIVATE_RELEASE_TAG=""
NO_PRIVATE_RELEASE_ASSETS=0

usage() {
  cat <<'EOF'
Usage:
  scripts/publish-public-source-release.sh [--repo OWNER/REPO] [--tag vX.Y.Z] [--private-release-tag TAG | --no-private-release-assets] [--dry-run] [--skip-public-check]

Creates a source-only GitHub Release for the public source version. It never
uploads binary assets. GitHub will still show the standard source archive links.

Options:
  --repo OWNER/REPO      GitHub repository. Defaults to current gh repo.
  --tag vX.Y.Z           Release tag. Defaults to v$(cat VERSION).
  --private-release-tag TAG
                         Existing private preview release to inspect before real publishing.
  --no-private-release-assets
                         Assert there are no private binary release assets to inspect.
  --dry-run              Print the planned tag/release actions only.
  --skip-public-check    Allow dry-run planning while the repository is still private.
EOF
}

local_tag_commit() {
  if git -C "${ROOT}" rev-parse -q --verify "refs/tags/$1" >/dev/null; then
    git -C "${ROOT}" rev-list -n 1 "$1"
  fi
}

remote_tag_commit() {
  git -C "${ROOT}" ls-remote --tags origin "refs/tags/$1" "refs/tags/$1^{}" |
    awk -v tag="$1" '
      $2 == "refs/tags/" tag "^{}" { peeled = $1 }
      $2 == "refs/tags/" tag { direct = $1 }
      END {
        if (peeled != "") {
          print peeled
        } else if (direct != "") {
          print direct
        }
      }
    '
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --tag) TAG="$2"; shift ;;
    --private-release-tag) PRIVATE_RELEASE_TAG="$2"; shift ;;
    --no-private-release-assets) NO_PRIVATE_RELEASE_ASSETS=1 ;;
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
if [ -n "${PRIVATE_RELEASE_TAG}" ] && [ "${NO_PRIVATE_RELEASE_ASSETS}" -eq 1 ]; then
  echo "[FAIL] use either --private-release-tag or --no-private-release-assets, not both" >&2
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
if ! "${ROOT}/scripts/verify-public-release-git-state.sh"; then
  exit 1
fi

if [ "${DRY_RUN}" -eq 0 ]; then
  if [ -z "${PRIVATE_RELEASE_TAG}" ] && [ "${NO_PRIVATE_RELEASE_ASSETS}" -ne 1 ]; then
    echo "[FAIL] real public publishing requires --private-release-tag TAG or --no-private-release-assets" >&2
    exit 2
  fi

  public_audit_args=(--repo "${REPO}" --require-public)
  prepare_args=(--repo "${REPO}")
  if [ -n "${PRIVATE_RELEASE_TAG}" ]; then
    public_audit_args+=(--release-tag "${PRIVATE_RELEASE_TAG}")
    prepare_args+=(--private-release-tag "${PRIVATE_RELEASE_TAG}")
  else
    prepare_args+=(--no-private-release-assets)
  fi

  "${ROOT}/scripts/audit-public-release.sh" "${public_audit_args[@]}"
  "${ROOT}/scripts/prepare-public-source-release.sh" "${prepare_args[@]}" --dry-run
elif [ -n "${PRIVATE_RELEASE_TAG}" ] || [ "${NO_PRIVATE_RELEASE_ASSETS}" -eq 1 ]; then
  echo "[DRY-RUN] final public gate arguments were supplied, but real public gates are only enforced when publishing."
fi

if ! git -C "${ROOT}" diff --quiet || ! git -C "${ROOT}" diff --cached --quiet; then
  echo "[FAIL] git worktree is dirty; commit or discard changes before release" >&2
  exit 1
fi

target="$(git -C "${ROOT}" rev-parse HEAD)"
local_existing="$(local_tag_commit "${TAG}")"
remote_existing="$(remote_tag_commit "${TAG}")"
if [ -n "${local_existing}" ] && [ "${local_existing}" != "${target}" ]; then
  echo "[FAIL] local tag ${TAG} points at ${local_existing}, expected ${target}" >&2
  exit 1
fi
if [ -n "${remote_existing}" ] && [ "${remote_existing}" != "${target}" ]; then
  echo "[FAIL] remote tag ${TAG} points at ${remote_existing}, expected ${target}" >&2
  exit 1
fi

echo "Repository: ${REPO} (${visibility})"
echo "Tag:        ${TAG}"
echo "Target:     ${target}"
if [ -n "${local_existing}" ] || [ -n "${remote_existing}" ]; then
  echo "Tag status: existing tag already points at target"
else
  echo "Tag status: will create annotated tag"
fi
echo "Title:      ${TITLE}"
echo "Notes:      ${NOTES_FILE}"
echo "Assets:     none"

if [ "${DRY_RUN}" -eq 1 ]; then
  echo "Dry run only; no tag or release was created."
  exit 0
fi

if [ -z "${local_existing}" ] && [ -z "${remote_existing}" ]; then
  git -C "${ROOT}" tag -a "${TAG}" -m "${TAG}"
fi
if [ -n "${remote_existing}" ] && [ -z "${local_existing}" ]; then
  git -C "${ROOT}" fetch origin "refs/tags/${TAG}:refs/tags/${TAG}"
elif [ -z "${remote_existing}" ]; then
  git -C "${ROOT}" push origin "${TAG}"
else
  echo "[release] remote tag ${TAG} already points at target"
fi

if gh release view "${TAG}" --repo "${REPO}" >/dev/null 2>&1; then
  gh release edit "${TAG}" --repo "${REPO}" --title "${TITLE}" --notes-file "${NOTES_FILE}" --target "${target}" --latest
else
  gh release create "${TAG}" --repo "${REPO}" --title "${TITLE}" --notes-file "${NOTES_FILE}" --target "${target}" --latest
fi

"${ROOT}/scripts/verify-public-source-release.sh" --repo "${REPO}" --tag "${TAG}" --expected-target "${target}"
