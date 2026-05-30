#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="${GITHUB_REPOSITORY:-}"
RELEASE_TAG=""
REQUIRE_PUBLIC=0
UPSTREAM_APPROVAL_FILE="${ROOT}/docs/UPSTREAM_TERMS_APPROVAL.md"

usage() {
  cat <<'EOF'
Usage:
  scripts/audit-public-release.sh [--repo OWNER/REPO] [--release-tag TAG] [--require-public]

Runs the normal source audit, then checks public-release blockers that require
maintainer/legal decisions before changing repository visibility.

This script intentionally fails while the project is still in private-preview
posture. Do not bypass failures for a public release; resolve them or keep the
repository private.

Options:
  --repo OWNER/REPO       GitHub repository. Defaults to current gh repo.
  --release-tag TAG       Optional release tag whose asset names must be checked.
  --require-public        Also fail if the GitHub repository is still private.

Human decision acknowledgements:
  DEEPCODEX_PUBLIC_BRAND_APPROVED=1
  DEEPCODEX_PUBLIC_UPSTREAM_TERMS_APPROVED=1
  DEEPCODEX_PUBLIC_BINARY_RELEASE_APPROVED=1

Durable approval file:
  docs/UPSTREAM_TERMS_APPROVAL.md
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --release-tag) RELEASE_TAG="$2"; shift ;;
    --require-public) REQUIRE_PUBLIC=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
fi

failures=0

block() {
  echo "[BLOCK] $*" >&2
  failures=$((failures + 1))
}

ok() {
  echo "[OK] $*"
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

public_binary_release_approved() {
  [ "${DEEPCODEX_PUBLIC_BINARY_RELEASE_APPROVED:-}" = "1" ] ||
    { [ -f "${UPSTREAM_APPROVAL_FILE}" ] &&
      grep -Eq '^public-binary-release:[[:space:]]*approved[[:space:]]*$' "${UPSTREAM_APPROVAL_FILE}"; }
}

echo "== Source release audit =="
"${ROOT}/scripts/audit-release.sh"

echo "== Git worktree =="
if git -C "${ROOT}" diff --quiet && git -C "${ROOT}" diff --cached --quiet; then
  ok "git worktree has no unstaged or staged changes"
else
  block "git worktree is dirty; commit or discard local changes before a public release"
fi
if "${ROOT}/scripts/verify-public-release-git-state.sh"; then
  ok "public release git state is synchronized with origin/main"
else
  block "public release must run from synchronized main branch"
fi

echo "== License posture =="
if grep -Eq 'No public open-source license is granted yet|Private Preview Notice' "${ROOT}/LICENSE.md"; then
  block "LICENSE.md is still a private-preview notice; choose a public license or keep source-available intentionally"
else
  ok "LICENSE.md no longer contains the private-preview notice"
fi

echo "== Version and public release notes posture =="
if [ -f "${ROOT}/VERSION" ] && grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' "${ROOT}/VERSION"; then
  ok "VERSION is a semver release version: $(cat "${ROOT}/VERSION")"
else
  block "VERSION must exist and contain a semver value like 0.1.0"
fi
if [ -s "${ROOT}/docs/PUBLIC_SOURCE_RELEASE_NOTES.md" ] &&
  grep -Eq 'v[0-9]+\.[0-9]+\.[0-9]+' "${ROOT}/docs/PUBLIC_SOURCE_RELEASE_NOTES.md" &&
  grep -Eq 'What Is Included|What Is Not Included|Public Release Preconditions' "${ROOT}/docs/PUBLIC_SOURCE_RELEASE_NOTES.md"; then
  ok "public source release notes are present"
else
  block "docs/PUBLIC_SOURCE_RELEASE_NOTES.md must describe the public source release"
fi

echo "== Brand and trademark posture =="
if git -C "${ROOT}" ls-files | grep -Eq '(^assets/brand/deepseek-|^assets/brand/deepcodex-hero\.png$)' || grep -Eiq 'Official DeepSeek Assets|downloaded from https://(cdn|download)\.deepseek\.com|official DeepSeek favicon|DeepSeek whale mark' "${ROOT}/assets/brand/SOURCES.md"; then
  if [ "${DEEPCODEX_PUBLIC_BRAND_APPROVED:-}" = "1" ]; then
    ok "third-party DeepSeek brand assets are tracked and were explicitly approved for public visibility"
  else
    block "third-party DeepSeek official/derived assets are still tracked or documented; replace them or set DEEPCODEX_PUBLIC_BRAND_APPROVED=1 after approval"
  fi
else
  ok "no DeepSeek official/derived brand assets are tracked"
fi

echo "== Upstream terms posture =="
if [ "${DEEPCODEX_PUBLIC_UPSTREAM_TERMS_APPROVED:-}" = "1" ]; then
  ok "upstream Codex patching/distribution terms were explicitly approved"
elif [ -f "${UPSTREAM_APPROVAL_FILE}" ] &&
  grep -Eq '^approval-status:[[:space:]]*approved[[:space:]]*$' "${UPSTREAM_APPROVAL_FILE}" &&
  grep -Eq '^public-source-release:[[:space:]]*approved[[:space:]]*$' "${UPSTREAM_APPROVAL_FILE}"; then
  ok "upstream Codex patching/distribution terms approval file is present"
else
  block "upstream Codex patching/distribution terms are not approved; keep the repository private until docs/UPSTREAM_TERMS_APPROVAL.md is completed"
fi

echo "== CI posture =="
if [ -f "${ROOT}/.github/workflows/audit.yml" ]; then
  ok "GitHub Actions audit workflow is present"
else
  block "GitHub Actions audit workflow is missing; add .github/workflows/audit.yml before public release"
  echo "       Template: docs/GITHUB_ACTIONS_AUDIT_TEMPLATE.yml" >&2
fi
if [ -n "${REPO}" ]; then
  if "${ROOT}/scripts/verify-github-actions-audit.sh" --repo "${REPO}" --commit "$(git -C "${ROOT}" rev-parse HEAD)"; then
    ok "GitHub Actions audit workflow passed for current commit"
  else
    block "GitHub Actions audit workflow has not passed for the current commit"
  fi
fi

echo "== README affiliation posture =="
if grep -Eiq 'not affiliated|not endorsed|unofficial' "${ROOT}/README.md" && grep -Eq '非官方|不隶属|未获.*背书|不代表.*官方' "${ROOT}/README.zh-CN.md"; then
  ok "English and Chinese README files state the unofficial/non-affiliation boundary"
else
  block "README files must state the unofficial/non-affiliation boundary in both languages"
fi

echo "== Public repository operations posture =="
required_public_files=(
  "CONTRIBUTING.md"
  "SUPPORT.md"
  "SECURITY.md"
  ".github/ISSUE_TEMPLATE/config.yml"
  ".github/ISSUE_TEMPLATE/bug_report.yml"
  ".github/ISSUE_TEMPLATE/docs.yml"
  ".github/ISSUE_TEMPLATE/release_readiness.yml"
  ".github/PULL_REQUEST_TEMPLATE.md"
  "scripts/verify-public-release-git-state.sh"
  "scripts/verify-github-actions-audit.sh"
  "scripts/publish-public-source-release.sh"
  "scripts/verify-public-source-release.sh"
)
for public_file in "${required_public_files[@]}"; do
  if [ -s "${ROOT}/${public_file}" ]; then
    ok "public operations file present: ${public_file}"
  else
    block "missing public operations file: ${public_file}"
  fi
done

if [ -n "${REPO}" ]; then
  echo "== GitHub repository metadata =="
  if "${ROOT}/scripts/verify-github-public-metadata.sh" --repo "${REPO}"; then
    ok "GitHub public metadata gate passed"
  else
    block "GitHub public metadata gate failed"
  fi

  repo_visibility_file="$(mktemp)"
  if retry_stdout "${repo_visibility_file}" gh repo view "${REPO}" --json isPrivate; then
    visibility_private="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("isPrivate"))' "${repo_visibility_file}")"
  else
    block "could not inspect GitHub repository visibility"
    visibility_private="unknown"
  fi
  rm -f "${repo_visibility_file}" "${repo_visibility_file}.tmp"

  if [ "${REQUIRE_PUBLIC}" -eq 1 ] && [ "${visibility_private}" = "true" ]; then
    block "repository is still private but --require-public was requested"
  elif [ "${visibility_private}" = "true" ]; then
    ok "repository is still private, which is correct until blockers are resolved"
  else
    ok "repository is public"
  fi
fi

if [ -n "${RELEASE_TAG}" ]; then
  echo "== Release asset names =="
  "${ROOT}/scripts/verify-release-assets.sh" --repo "${REPO}" --tag "${RELEASE_TAG}"

  release_assets_file="$(mktemp)"
  if ! retry_stdout "${release_assets_file}" gh release view "${RELEASE_TAG}" --repo "${REPO}" --json assets -q '.assets[].name'; then
    block "could not inspect release assets for ${RELEASE_TAG}"
    release_assets=""
  else
    release_assets="$(cat "${release_assets_file}")"
  fi
  rm -f "${release_assets_file}" "${release_assets_file}.tmp"
  if [ -n "${release_assets:-}" ] && printf '%s\n' "${release_assets}" | grep -Eq '\.(app|asar|dmg|pkg|zip|tar|tar\.gz|tgz|7z|rar)(\.sha256)?$'; then
    if public_binary_release_approved; then
      ok "public binary release assets are explicitly approved"
    else
      block "release ${RELEASE_TAG} contains binary assets; remove them or complete public-binary-release approval before public visibility"
    fi
  fi
fi

if [ "${failures}" -gt 0 ]; then
  echo "Public release audit failed with ${failures} blocker(s)." >&2
  exit 1
fi

echo "Public release audit passed."
