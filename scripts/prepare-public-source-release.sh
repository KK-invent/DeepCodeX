#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="${GITHUB_REPOSITORY:-}"
PRIVATE_RELEASE_TAG=""
NO_PRIVATE_RELEASE_ASSETS=0
DELETE_BINARY_ASSETS=0
HIDE_PRIVATE_RELEASE=0
DRY_RUN=0
APPROVAL_FILE="${ROOT}/docs/UPSTREAM_TERMS_APPROVAL.md"

usage() {
  cat <<'EOF'
Usage:
  scripts/prepare-public-source-release.sh [--repo OWNER/REPO] --private-release-tag TAG [--delete-binary-assets] [--hide-private-release] [--dry-run]
  scripts/prepare-public-source-release.sh [--repo OWNER/REPO] --no-private-release-assets [--dry-run]

Preflights the final source-only public release path.

The script does not make the repository public. It verifies the committed source
surface, durable upstream approval, GitHub Actions audit workflow, and private
binary release asset posture. If public binary distribution is not approved,
the script can remove private preview binary assets before visibility changes.

Options:
  --repo OWNER/REPO            GitHub repository. Defaults to current gh repo.
  --private-release-tag TAG    Existing private preview release to inspect.
  --no-private-release-assets  Explicitly assert there is no private binary release to inspect.
  --delete-binary-assets       Delete binary/checksum assets from that release when public-binary-release is private-only.
  --hide-private-release       Mark the inspected private preview release as draft after binary assets are removed.
  --dry-run                    Print what would be deleted, but do not delete assets.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --private-release-tag) PRIVATE_RELEASE_TAG="$2"; shift ;;
    --no-private-release-assets) NO_PRIVATE_RELEASE_ASSETS=1 ;;
    --delete-binary-assets) DELETE_BINARY_ASSETS=1 ;;
    --hide-private-release) HIDE_PRIVATE_RELEASE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
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
    *.app|*.app.sha256|*.asar|*.asar.sha256|*.dmg|*.dmg.sha256|*.pkg|*.pkg.sha256|*.zip|*.zip.sha256|*.tar|*.tar.sha256|*.tar.gz|*.tar.gz.sha256|*.tgz|*.tgz.sha256|*.7z|*.7z.sha256|*.rar|*.rar.sha256)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

collect_binary_assets_for_release() {
  local tag="$1"
  local assets="${tmp}/assets-${tag//[^A-Za-z0-9_.-]/_}.txt"
  retry_stdout "${assets}" gh release view "${tag}" --repo "${REPO}" --json assets -q '.assets[] | "\(.id)\t\(.name)"' || return 1
  while IFS=$'\t' read -r asset_id asset_name; do
    [ -n "${asset_id:-}" ] || continue
    if is_binary_release_asset "${asset_name}"; then
      printf '%s\t%s\t%s\n' "${tag}" "${asset_id}" "${asset_name}"
    fi
  done < "${assets}"
}

release_is_draft() {
  local tag="$1"
  local draft_file="${tmp}/draft-${tag//[^A-Za-z0-9_.-]/_}.txt"
  retry_stdout "${draft_file}" gh release view "${tag}" --repo "${REPO}" --json isDraft -q '.isDraft' || return 1
  [ "$(tr '[:upper:]' '[:lower:]' < "${draft_file}")" = "true" ]
}

release_exists() {
  retry gh release view "$1" --repo "${REPO}" --json tagName >/dev/null
}

mark_private_release_draft() {
  local tag="$1"
  if [ "${HIDE_PRIVATE_RELEASE}" -ne 1 ]; then
    return 0
  fi
  if [ "${SOURCE_APPROVAL_READY}" -ne 1 ]; then
    block "refusing to hide private release before docs/UPSTREAM_TERMS_APPROVAL.md is completed"
  elif [ "${binary_status:-}" != "private-only" ]; then
    block "refusing to hide private release unless public-binary-release is private-only"
  elif [ "${DRY_RUN}" -eq 1 ]; then
    echo "[DRY-RUN] would mark ${tag} as draft"
  elif release_is_draft "${tag}"; then
    ok "release ${tag} is already draft"
  else
    echo "[draft] ${tag}"
    gh release edit "${tag}" --repo "${REPO}" --draft >/dev/null
    if release_is_draft "${tag}"; then
      ok "release ${tag} is draft"
    else
      block "release ${tag} was not marked draft"
    fi
  fi
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
if "${ROOT}/scripts/verify-public-release-git-state.sh"; then
  ok "public release git state is synchronized with origin/main"
else
  block "public release must run from synchronized main branch"
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
if "${ROOT}/scripts/verify-github-actions-audit.sh" --repo "${REPO}" --commit "$(git -C "${ROOT}" rev-parse HEAD)"; then
  ok "GitHub Actions audit workflow passed for current commit"
else
  block "GitHub Actions audit workflow has not passed for the current commit"
fi

echo "== Private preview release assets =="
binary_status="${binary_status:-$(approval_value public-binary-release)}"
binary_assets=()
all_release_binary_assets=()
if [ "${NO_PRIVATE_RELEASE_ASSETS}" -eq 1 ] && [ -n "${PRIVATE_RELEASE_TAG}" ]; then
  block "use either --private-release-tag or --no-private-release-assets, not both"
elif [ "${DELETE_BINARY_ASSETS}" -eq 1 ] && [ "${NO_PRIVATE_RELEASE_ASSETS}" -eq 1 ]; then
  block "--delete-binary-assets requires --private-release-tag"
elif [ "${HIDE_PRIVATE_RELEASE}" -eq 1 ] && [ "${NO_PRIVATE_RELEASE_ASSETS}" -eq 1 ]; then
  block "--hide-private-release requires --private-release-tag"
elif [ "${HIDE_PRIVATE_RELEASE}" -eq 1 ] && [ "${DELETE_BINARY_ASSETS}" -ne 1 ]; then
  block "--hide-private-release requires --delete-binary-assets"
elif [ -n "${PRIVATE_RELEASE_TAG}" ]; then
  if ! release_exists "${PRIVATE_RELEASE_TAG}"; then
    block "private release tag not found or could not be inspected: ${PRIVATE_RELEASE_TAG}"
  else
    if ! binary_asset_rows="$(collect_binary_assets_for_release "${PRIVATE_RELEASE_TAG}")"; then
      block "could not inspect binary assets for release ${PRIVATE_RELEASE_TAG}"
      binary_asset_rows=""
    fi
    while IFS=$'\t' read -r release_tag asset_id asset_name; do
      [ -n "${asset_id:-}" ] || continue
      binary_assets+=("${asset_id}"$'\t'"${asset_name}")
    done <<< "${binary_asset_rows}"

    if [ "${#binary_assets[@]}" -eq 0 ]; then
      ok "no binary/checksum assets are attached to ${PRIVATE_RELEASE_TAG}"
      mark_private_release_draft "${PRIVATE_RELEASE_TAG}"
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
        mark_private_release_draft "${PRIVATE_RELEASE_TAG}"
      fi
    else
      block "release ${PRIVATE_RELEASE_TAG} still has binary/checksum assets; rerun with --delete-binary-assets after approval, or keep the repo private"
      printf '%s\n' "${binary_assets[@]}" | cut -f2 | sed 's/^/  - /' >&2
    fi
  fi
elif [ "${NO_PRIVATE_RELEASE_ASSETS}" -eq 1 ]; then
  release_tags="${tmp}/release-tags.txt"
  release_list_ready=1
  if ! retry_stdout "${release_tags}" gh release list --repo "${REPO}" --limit 100 --json tagName -q '.[].tagName'; then
    block "could not list GitHub releases for ${REPO}"
    release_list_ready=0
  else
    while IFS= read -r release_tag; do
      [ -n "${release_tag:-}" ] || continue
      if ! binary_asset_rows="$(collect_binary_assets_for_release "${release_tag}")"; then
        block "could not inspect binary assets for release ${release_tag}"
        binary_asset_rows=""
      fi
      while IFS=$'\t' read -r found_tag asset_id asset_name; do
        [ -n "${asset_id:-}" ] || continue
        all_release_binary_assets+=("${found_tag}"$'\t'"${asset_id}"$'\t'"${asset_name}")
      done <<< "${binary_asset_rows}"
    done < "${release_tags}"
  fi

  if [ "${release_list_ready}" -eq 1 ] && [ "${#all_release_binary_assets[@]}" -eq 0 ]; then
    ok "no binary/checksum assets found across GitHub releases"
  elif [ "${#all_release_binary_assets[@]}" -gt 0 ]; then
    block "--no-private-release-assets was supplied, but binary/checksum assets exist on GitHub releases"
    printf '%s\n' "${all_release_binary_assets[@]}" | awk -F '\t' '{ print "  - " $1 ": " $3 }' >&2
  fi
else
  block "supply --private-release-tag TAG to inspect private preview release assets, or pass --no-private-release-assets if none exist"
fi

if [ "${failures}" -gt 0 ]; then
  echo "Public source release preflight failed with ${failures} blocker(s)." >&2
  exit 1
fi

echo "Public source release preflight passed."
echo "Next manual step, after reviewing GitHub UI:"
echo "  gh repo edit ${REPO} --visibility public --accept-visibility-change-consequences"
