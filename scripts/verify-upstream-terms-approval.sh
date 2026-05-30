#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPROVAL_FILE="${ROOT}/docs/UPSTREAM_TERMS_APPROVAL.md"
TERMS_REVIEW_FILE="${ROOT}/docs/UPSTREAM_TERMS_REVIEW.md"
REQUIRE_BINARY_APPROVED=0

usage() {
  cat <<'EOF'
Usage:
  scripts/verify-upstream-terms-approval.sh [--file FILE] [--terms-review FILE] [--require-binary-approved]

Verifies that the durable upstream terms approval file is complete enough to
unlock public release gates. This does not grant legal approval; it only checks
that a real approval record is present and not a mostly blank template.

Options:
  --file FILE                  Approval file to verify. Defaults to docs/UPSTREAM_TERMS_APPROVAL.md.
  --terms-review FILE          Terms review file to compare against. Defaults to docs/UPSTREAM_TERMS_REVIEW.md.
  --require-binary-approved    Require public-binary-release: approved.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --file) APPROVAL_FILE="$2"; shift ;;
    --terms-review) TERMS_REVIEW_FILE="$2"; shift ;;
    --require-binary-approved) REQUIRE_BINARY_APPROVED=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

failures=0

fail() {
  echo "[FAIL] $*" >&2
  failures=$((failures + 1))
}

ok() {
  echo "[OK] $*"
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

date_number() {
  printf '%s\n' "$1" | tr -d '-'
}

terms_review_last_checked() {
  awk -F: '
    $1 == "Last checked" {
      value = $0
      sub("^[^:]*:[[:space:]]*", "", value)
      sub("[.][[:space:]]*$", "", value)
      sub("[[:space:]]*$", "", value)
      print value
      exit
    }
  ' "${TERMS_REVIEW_FILE}" 2>/dev/null || true
}

require_exact_value() {
  local key="$1"
  local expected="$2"
  local actual
  actual="$(approval_value "${key}")"
  if [ "${actual}" = "${expected}" ]; then
    ok "${key} is ${expected}"
  else
    fail "${key} must be ${expected}; got '${actual:-empty}'"
  fi
}

if [ ! -f "${APPROVAL_FILE}" ]; then
  fail "missing ${APPROVAL_FILE}; copy docs/UPSTREAM_TERMS_APPROVAL_TEMPLATE.md only after real approval"
else
  require_exact_value approval-status approved
  require_exact_value public-source-release approved

  reviewer="$(approval_value reviewer)"
  if [ -z "${reviewer}" ] || printf '%s\n' "${reviewer}" | grep -Eiq '^(todo|tbd|n/a|none|reviewer)$'; then
    fail "reviewer must name the maintainer or legal reviewer"
  else
    ok "reviewer is recorded"
  fi

  review_date="$(approval_value review-date)"
  if printf '%s\n' "${review_date}" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
    ok "review-date is ${review_date}"
    today="$(date '+%Y-%m-%d')"
    if [ "$(date_number "${review_date}")" -gt "$(date_number "${today}")" ]; then
      fail "review-date cannot be in the future; got ${review_date}, today is ${today}"
    fi
    terms_checked="$(terms_review_last_checked)"
    if ! printf '%s\n' "${terms_checked}" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
      fail "terms review file must record 'Last checked: YYYY-MM-DD.'; got '${terms_checked:-empty}'"
    elif [ "$(date_number "${review_date}")" -lt "$(date_number "${terms_checked}")" ]; then
      fail "review-date ${review_date} is older than ${TERMS_REVIEW_FILE} Last checked: ${terms_checked}"
    else
      ok "review-date is current with terms review checked on ${terms_checked}"
    fi
  else
    fail "review-date must use YYYY-MM-DD; got '${review_date:-empty}'"
  fi

  binary_status="$(approval_value public-binary-release)"
  case "${binary_status}" in
    private-only|approved)
      ok "public-binary-release is ${binary_status}"
      ;;
    *)
      fail "public-binary-release must be private-only or approved; got '${binary_status:-empty}'"
      ;;
  esac
  if [ "${REQUIRE_BINARY_APPROVED}" -eq 1 ] && [ "${binary_status}" != "approved" ]; then
    fail "public-binary-release must be approved for public binary assets"
  fi

  required_terms=(
    "OpenAI Terms of Use"
    "OpenAI Service Terms"
    "OpenAI Services Agreement"
    "OpenAI Help Center"
    "OpenAI Codex product page"
  )
  for term in "${required_terms[@]}"; do
    if grep -Fq "${term}" "${APPROVAL_FILE}"; then
      ok "terms-reviewed includes ${term}"
    else
      fail "terms-reviewed must include ${term}"
    fi
  done
fi

if [ "${failures}" -gt 0 ]; then
  echo "Upstream terms approval verification failed with ${failures} issue(s)." >&2
  exit 1
fi

echo "Upstream terms approval verified: ${APPROVAL_FILE}"
