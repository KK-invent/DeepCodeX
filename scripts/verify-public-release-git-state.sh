#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="main"
REMOTE="origin"

usage() {
  cat <<'EOF'
Usage:
  scripts/verify-public-release-git-state.sh [--branch NAME] [--remote NAME]

Verifies that the public release is being prepared from the expected branch and
that the local HEAD exactly matches the remote branch tip.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --branch) BRANCH="$2"; shift ;;
    --remote) REMOTE="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

current_branch="$(git -C "${ROOT}" symbolic-ref --short -q HEAD || true)"
head_sha="$(git -C "${ROOT}" rev-parse HEAD)"

if [ "${current_branch}" != "${BRANCH}" ]; then
  echo "[BLOCK] public release must run from branch ${BRANCH}; current branch is ${current_branch:-detached}" >&2
  exit 1
fi

remote_sha="$(git -C "${ROOT}" ls-remote "${REMOTE}" "refs/heads/${BRANCH}" | awk '{ print $1; exit }')"
if [ -z "${remote_sha}" ]; then
  echo "[BLOCK] could not resolve ${REMOTE}/${BRANCH}" >&2
  exit 1
fi

if [ "${head_sha}" != "${remote_sha}" ]; then
  echo "[BLOCK] local HEAD ${head_sha} does not match ${REMOTE}/${BRANCH} ${remote_sha}" >&2
  exit 1
fi

echo "[OK] local ${BRANCH} is synchronized with ${REMOTE}/${BRANCH}: ${head_sha}"
