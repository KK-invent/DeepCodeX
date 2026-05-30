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

tmp="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp}"
}
trap cleanup EXIT

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

failures=0

block() {
  echo "[BLOCK] $*" >&2
  failures=$((failures + 1))
}

ok() {
  echo "[OK] $*"
}

repo_json="${tmp}/repo.json"
labels_json="${tmp}/labels.json"
if ! retry_stdout "${repo_json}" gh repo view "${REPO}" --json description,homepageUrl,licenseInfo,repositoryTopics; then
  block "could not inspect GitHub repository metadata"
  echo "GitHub public metadata verification failed with ${failures} issue(s)." >&2
  exit 1
fi
if ! retry_stdout "${labels_json}" gh label list --repo "${REPO}" --limit 100 --json name; then
  block "could not inspect GitHub labels"
  echo "GitHub public metadata verification failed with ${failures} issue(s)." >&2
  exit 1
fi

description="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("description") or "")' "${repo_json}")"
homepage="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("homepageUrl") or "")' "${repo_json}")"
license_key="$(python3 -c 'import json,sys; print((json.load(open(sys.argv[1])).get("licenseInfo") or {}).get("key") or "")' "${repo_json}")"
topics="$(python3 -c 'import json,sys; print(" ".join(sorted(topic.get("name","") for topic in json.load(open(sys.argv[1])).get("repositoryTopics", []))))' "${repo_json}")"
labels="$(python3 -c 'import json,sys; print(" ".join(sorted(label.get("name","") for label in json.load(open(sys.argv[1])))))' "${labels_json}")"

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
