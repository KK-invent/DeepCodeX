#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${ROOT}/docs/GITHUB_ACTIONS_AUDIT_TEMPLATE.yml"
TARGET="${ROOT}/.github/workflows/audit.yml"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is required to check token scopes before creating the workflow." >&2
  exit 1
fi

auth_status="$(gh auth status -h github.com 2>&1 || true)"
if ! printf '%s\n' "${auth_status}" | grep -Eq "Token scopes: .*'workflow'"; then
  cat >&2 <<'EOF'
The active GitHub token does not have the workflow scope.

Run:
  gh auth refresh -h github.com -s workflow

Then rerun:
  scripts/enable-github-actions-audit.sh
EOF
  exit 1
fi

mkdir -p "$(dirname "${TARGET}")"
cp "${TEMPLATE}" "${TARGET}"
echo "Created ${TARGET}"
