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

echo "== Source release audit =="
"${ROOT}/scripts/audit-release.sh"

echo "== Git worktree =="
if git -C "${ROOT}" diff --quiet && git -C "${ROOT}" diff --cached --quiet; then
  ok "git worktree has no unstaged or staged changes"
else
  block "git worktree is dirty; commit or discard local changes before a public release"
fi

echo "== License posture =="
if grep -Eq 'No public open-source license is granted yet|Private Preview Notice' "${ROOT}/LICENSE.md"; then
  block "LICENSE.md is still a private-preview notice; choose a public license or keep source-available intentionally"
else
  ok "LICENSE.md no longer contains the private-preview notice"
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
  description="$(gh repo view "${REPO}" --json description -q .description)"
  homepage="$(gh repo view "${REPO}" --json homepageUrl -q .homepageUrl)"
  visibility_private="$(gh repo view "${REPO}" --json isPrivate -q .isPrivate)"
  license_key="$(gh repo view "${REPO}" --json licenseInfo -q '.licenseInfo.key // ""')"
  topics="$(gh repo view "${REPO}" --json repositoryTopics -q '.repositoryTopics[].name' | sort | tr '\n' ' ')"

  [ -n "${description}" ] && ok "repository description is set" || block "repository description is empty"
  [ -n "${homepage}" ] && ok "repository homepage is set" || block "repository homepage is empty"

  for topic in ai codex deepseek developer-tools macos; do
    if printf '%s\n' "${topics}" | grep -Eq "(^| )${topic}( |$)"; then
      ok "topic present: ${topic}"
    else
      block "missing GitHub topic: ${topic}"
    fi
  done

  if command -v gh >/dev/null 2>&1; then
    labels="$(gh label list --repo "${REPO}" --limit 100 --json name -q '.[].name' | sort | tr '\n' ' ')"
    for label in bug documentation release; do
      if printf '%s\n' "${labels}" | grep -Eq "(^| )${label}( |$)"; then
        ok "label present: ${label}"
      else
        block "missing GitHub label used by issue templates: ${label}"
      fi
    done
  fi

  if [ "${license_key}" = "other" ] || [ -z "${license_key}" ]; then
    block "GitHub license detection is '${license_key:-empty}'; choose an explicit public license before public release"
  else
    ok "GitHub detected license: ${license_key}"
  fi

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

  if [ "${REQUIRE_PUBLIC}" -eq 1 ]; then
    release_assets="$(gh release view "${RELEASE_TAG}" --repo "${REPO}" --json assets -q '.assets[].name' 2>/dev/null || true)"
    if printf '%s\n' "${release_assets}" | grep -Eq '\.(app|asar|dmg|pkg|zip)$'; then
      if [ "${DEEPCODEX_PUBLIC_BINARY_RELEASE_APPROVED:-}" = "1" ] ||
        { [ -f "${UPSTREAM_APPROVAL_FILE}" ] &&
          grep -Eq '^public-binary-release:[[:space:]]*approved[[:space:]]*$' "${UPSTREAM_APPROVAL_FILE}"; }; then
        ok "public binary release assets are explicitly approved"
      else
        block "release ${RELEASE_TAG} contains binary assets; remove them or complete public-binary-release approval before public visibility"
      fi
    fi
  fi
fi

if [ "${failures}" -gt 0 ]; then
  echo "Public release audit failed with ${failures} blocker(s)." >&2
  exit 1
fi

echo "Public release audit passed."
