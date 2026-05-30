#!/usr/bin/env bash
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-}"

usage() {
  cat <<'EOF'
Usage:
  scripts/verify-github-public-metadata.sh [--repo OWNER/REPO]

Checks GitHub metadata that supports a public DeepCodeX repository: labels used
by issue templates, topics, homepage, description, and license detection.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi

failures=0

block() {
  echo "[BLOCK] $*" >&2
  failures=$((failures + 1))
}

ok() {
  echo "[OK] $*"
}

description="$(gh repo view "${REPO}" --json description -q .description)"
homepage="$(gh repo view "${REPO}" --json homepageUrl -q .homepageUrl)"
license_key="$(gh repo view "${REPO}" --json licenseInfo -q '.licenseInfo.key // ""')"
topics="$(gh repo view "${REPO}" --json repositoryTopics -q '.repositoryTopics[].name' | sort | tr '\n' ' ')"
labels="$(gh label list --repo "${REPO}" --limit 100 --json name -q '.[].name' | sort | tr '\n' ' ')"

[ -n "${description}" ] && ok "repository description is set" || block "repository description is empty"
[ -n "${homepage}" ] && ok "repository homepage is set" || block "repository homepage is empty"
[ "${license_key}" = "mit" ] && ok "GitHub detected license: mit" || block "GitHub license detection is '${license_key:-empty}'"

for topic in ai codex deepseek developer-tools macos; do
  if printf '%s\n' "${topics}" | grep -Eq "(^| )${topic}( |$)"; then
    ok "topic present: ${topic}"
  else
    block "missing GitHub topic: ${topic}"
  fi
done

for label in bug documentation release; do
  if printf '%s\n' "${labels}" | grep -Eq "(^| )${label}( |$)"; then
    ok "label present: ${label}"
  else
    block "missing GitHub label used by issue templates: ${label}"
  fi
done

if [ "${failures}" -gt 0 ]; then
  echo "GitHub public metadata verification failed with ${failures} issue(s)." >&2
  exit 1
fi

echo "GitHub public metadata verified: ${REPO}"
