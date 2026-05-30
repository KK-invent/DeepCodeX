#!/usr/bin/env bash
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-}"
TAG=""

usage() {
  cat <<'EOF'
Usage:
  scripts/verify-public-source-release.sh --tag vX.Y.Z [--repo OWNER/REPO]

Verifies that a public source GitHub Release has no uploaded binary assets.
GitHub's automatic source archive links are allowed.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift ;;
    --tag) TAG="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "${REPO}" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
if [ -z "${TAG}" ]; then
  echo "[FAIL] --tag is required" >&2
  usage >&2
  exit 2
fi

release_json="$(gh release view "${TAG}" --repo "${REPO}" --json tagName,isDraft,isPrerelease,assets)"
is_draft="$(printf '%s\n' "${release_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["isDraft"])')"
is_prerelease="$(printf '%s\n' "${release_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["isPrerelease"])')"
asset_names="$(printf '%s\n' "${release_json}" | python3 -c 'import json,sys; print("\n".join(a["name"] for a in json.load(sys.stdin)["assets"]))')"

failures=0
if [ "${is_draft}" != "False" ]; then
  echo "[BLOCK] release ${TAG} is still a draft" >&2
  failures=$((failures + 1))
fi
if [ "${is_prerelease}" != "False" ]; then
  echo "[BLOCK] release ${TAG} is marked prerelease" >&2
  failures=$((failures + 1))
fi
if [ -n "${asset_names}" ]; then
  echo "[BLOCK] public source release must not have uploaded assets:" >&2
  printf '%s\n' "${asset_names}" | sed 's/^/  - /' >&2
  failures=$((failures + 1))
fi

if [ "${failures}" -gt 0 ]; then
  echo "Public source release verification failed with ${failures} issue(s)." >&2
  exit 1
fi

echo "Public source release verified: ${REPO} ${TAG}"
