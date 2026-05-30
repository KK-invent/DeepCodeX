#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="${GITHUB_REPOSITORY:-}"
WORKFLOW="Audit"
COMMIT=""

usage() {
  cat <<'EOF'
Usage:
  scripts/verify-github-actions-audit.sh [--repo OWNER/REPO] [--workflow NAME] [--commit SHA]

Verifies that the GitHub Actions audit workflow has a successful run for the
exact commit being prepared for public release.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --workflow) WORKFLOW="$2"; shift ;;
    --commit) COMMIT="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
if [ -z "${COMMIT}" ]; then
  COMMIT="$(git -C "${ROOT}" rev-parse HEAD)"
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

runs_json="${tmp}/runs.json"
if ! retry_stdout "${runs_json}" gh run list \
  --repo "${REPO}" \
  --workflow "${WORKFLOW}" \
  --commit "${COMMIT}" \
  --limit 10 \
  --json databaseId,headSha,status,conclusion,displayTitle,createdAt,url; then
  echo "[BLOCK] could not inspect GitHub Actions workflow runs for ${REPO}" >&2
  exit 1
fi

python3 - "${runs_json}" "${WORKFLOW}" "${COMMIT}" <<'PY'
import json
import sys

runs_path, workflow, commit = sys.argv[1:]
with open(runs_path, encoding="utf-8") as fh:
    runs = json.load(fh)

exact_runs = [run for run in runs if run.get("headSha") == commit]
if not exact_runs:
    print(
        f"[BLOCK] no {workflow} workflow run found for commit {commit}",
        file=sys.stderr,
    )
    sys.exit(1)

successful = [
    run
    for run in exact_runs
    if run.get("status") == "completed" and run.get("conclusion") == "success"
]
if successful:
    run = successful[0]
    print(f"[OK] {workflow} workflow passed for {commit}: {run.get('url')}")
    sys.exit(0)

print(
    f"[BLOCK] no successful {workflow} workflow run found for commit {commit}",
    file=sys.stderr,
)
for run in exact_runs:
    print(
        "  - "
        f"{run.get('displayTitle')} "
        f"status={run.get('status')} "
        f"conclusion={run.get('conclusion')} "
        f"url={run.get('url')}",
        file=sys.stderr,
    )
sys.exit(1)
PY
