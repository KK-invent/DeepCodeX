#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="${GITHUB_REPOSITORY:-}"
PRIVATE_RELEASE_TAG=""
DELETE_BINARY_ASSETS=0
DRY_RUN=0
APPROVAL_FILE="${ROOT}/docs/UPSTREAM_TERMS_APPROVAL.md"

usage() {
  cat <<'EOF'
Usage:
  scripts/prepare-public-source-release.sh [--repo OWNER/REPO] [--private-release-tag TAG] [--delete-binary-assets] [--dry-run]

Preflights the final source-only public release path.

The script does not make the repository public. It verifies the committed source
surface, durable upstream approval, GitHub Actions audit workflow, and private
binary release asset posture. If public binary distribution is not approved,
the script can remove private preview binary assets before visibility changes.

Options:
  --repo OWNER/REPO            GitHub repository. Defaults to current gh repo.
  --private-release-tag TAG    Existing private preview release to inspect.
  --delete-binary-assets       Delete binary/checksum assets from that release when public-binary-release is private-only.
  --dry-run                    Print what would be deleted, but do not delete assets.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --private-release-tag) PRIVATE_RELEASE_TAG="$2"; shift ;;
    --delete-binary-assets) DELETE_BINARY_ASSETS=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi

approval_value() {
  local key="$1"
  awk -F: -v key="${key}" '
    $1 == key {
      value = $0
      sub("^[^:]*:[[:space:]]*", "", value)
      sub("[[:space:]]*$", "", value)
      print value
      exit
    }
  ' "${APPROVAL_FILE}" 2>/dev/null || true
}

is_binary_release_asset() {
  case "$1" in
    *.app|*.app.sha256|*.asar|*.asar.sha256|*.dmg|*.dmg.sha256|*.pkg|*.pkg.sha256|*.zip|*.zip.sha256)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

failures=0
SOURCE_APPROVAL_READY=0

block() {
  echo "[BLOCK] $*" >&2
  failures=$((failures + 1))
}

ok() {
  echo "[OK] $*"
}

echo "== Source audit =="
"${ROOT}/scripts/audit-release.sh"

echo "== Git worktree =="
if git -C "${ROOT}" diff --quiet && git -C "${ROOT}" diff --cached --quiet; then
  ok "git worktree has no unstaged or staged changes"
else
  block "git worktree is dirty; commit or discard changes before public visibility"
fi

echo "== GitHub repository =="
visibility="$(gh repo view "${REPO}" --json visibility -q .visibility)"
license_key="$(gh repo view "${REPO}" --json licenseInfo -q '.licenseInfo.key // ""')"
ok "repository visibility is ${visibility}"
if [ "${license_key}" = "mit" ]; then
  ok "GitHub detects MIT license"
else
  block "GitHub license detection is '${license_key:-empty}', expected mit"
fi

echo "== Durable upstream approval =="
if [ ! -f "${APPROVAL_FILE}" ]; then
  block "missing ${APPROVAL_FILE}; copy docs/UPSTREAM_TERMS_APPROVAL_TEMPLATE.md only after real approval"
else
  approval_status="$(approval_value approval-status)"
  source_status="$(approval_value public-source-release)"
  binary_status="$(approval_value public-binary-release)"

  [ "${approval_status}" = "approved" ] && ok "approval-status approved" || block "approval-status must be approved"
  [ "${source_status}" = "approved" ] && ok "public-source-release approved" || block "public-source-release must be approved"
  case "${binary_status}" in
    private-only|approved) ok "public-binary-release is ${binary_status}" ;;
    *) block "public-binary-release must be private-only or approved" ;;
  esac
  if [ "${approval_status}" = "approved" ] &&
    [ "${source_status}" = "approved" ] &&
    { [ "${binary_status}" = "private-only" ] || [ "${binary_status}" = "approved" ]; }; then
    SOURCE_APPROVAL_READY=1
  fi
fi

echo "== GitHub Actions audit =="
if [ -f "${ROOT}/.github/workflows/audit.yml" ]; then
  ok "GitHub Actions audit workflow is present"
else
  block "missing .github/workflows/audit.yml; run scripts/enable-github-actions-audit.sh after refreshing gh workflow scope"
fi

echo "== Private preview release assets =="
binary_status="${binary_status:-$(approval_value public-binary-release)}"
binary_assets=()
if [ -n "${PRIVATE_RELEASE_TAG}" ]; then
  while IFS=$'\t' read -r asset_id asset_name; do
    [ -n "${asset_id:-}" ] || continue
    if is_binary_release_asset "${asset_name}"; then
      binary_assets+=("${asset_id}"$'\t'"${asset_name}")
    fi
  done < <(gh release view "${PRIVATE_RELEASE_TAG}" --repo "${REPO}" --json assets -q '.assets[] | "\(.id)\t\(.name)"')

  if [ "${#binary_assets[@]}" -eq 0 ]; then
    ok "no binary/checksum assets are attached to ${PRIVATE_RELEASE_TAG}"
  elif [ "${binary_status:-}" = "approved" ]; then
    ok "binary release assets are present and public-binary-release is approved"
  elif [ "${DELETE_BINARY_ASSETS}" -eq 1 ]; then
    if [ "${SOURCE_APPROVAL_READY}" -ne 1 ]; then
      block "refusing to delete release assets before docs/UPSTREAM_TERMS_APPROVAL.md is completed"
    elif [ "${binary_status:-}" != "private-only" ]; then
      block "refusing to delete release assets unless public-binary-release is private-only"
    else
      for entry in "${binary_assets[@]}"; do
        asset_id="${entry%%$'\t'*}"
        asset_name="${entry#*$'\t'}"
        if [ "${DRY_RUN}" -eq 1 ]; then
          echo "[DRY-RUN] would delete ${asset_name} (${asset_id})"
        else
          echo "[delete] ${asset_name} (${asset_id})"
          gh api -X DELETE "repos/${REPO}/releases/assets/${asset_id}" >/dev/null
        fi
      done
    fi
  else
    block "release ${PRIVATE_RELEASE_TAG} still has binary/checksum assets; rerun with --delete-binary-assets after approval, or keep the repo private"
    printf '%s\n' "${binary_assets[@]}" | cut -f2 | sed 's/^/  - /' >&2
  fi
else
  ok "no private release tag supplied; skipping release asset cleanup"
fi

if [ "${failures}" -gt 0 ]; then
  echo "Public source release preflight failed with ${failures} blocker(s)." >&2
  exit 1
fi

echo "Public source release preflight passed."
echo "Next manual step, after reviewing GitHub UI:"
echo "  gh repo edit ${REPO} --visibility public --accept-visibility-change-consequences"
