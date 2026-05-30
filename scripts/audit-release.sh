#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

echo "== Python syntax =="
pycache_root="$(mktemp -d)"
cleanup() {
  rm -rf "${pycache_root}"
}
trap cleanup EXIT
PYTHONPYCACHEPREFIX="${pycache_root}" python3 -m py_compile bin/*.py

echo "== Image-strip self-test =="
python3 bin/deepcodex-image-strip-proxy.py --selftest

echo "== Banned source/runtime filenames =="
if find . \
  -path ./.git -prune -o \
  -path ./dist -prune -o \
  -path ./release-work -prune -o \
  \( -name '*.app' -o -name '*.app.sha256' -o -name '*.asar' -o -name '*.asar.*' -o -name '*.dmg' -o -name '*.dmg.sha256' -o -name '*.pkg' -o -name '*.pkg.sha256' -o -name '*.zip' -o -name '*.zip.sha256' -o -name '*.tar' -o -name '*.tar.sha256' -o -name '*.tar.gz' -o -name '*.tar.gz.sha256' -o -name '*.tgz' -o -name '*.tgz.sha256' -o -name '*.7z' -o -name '*.7z.sha256' -o -name '*.rar' -o -name '*.rar.sha256' -o -name '*.sqlite' -o -name '*.sqlite-*' -o -name '*.db' -o -name '*.db-*' -o -name '*.log' -o -name 'auth.json' -o -name 'secrets.env' -o \( -name 'config.json' -a -path './ccx/.config/*' \) -o -name '__pycache__' -o -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) \
  -print | grep -q .; then
  find . \
    -path ./.git -prune -o \
    -path ./dist -prune -o \
    -path ./release-work -prune -o \
    \( -name '*.app' -o -name '*.app.sha256' -o -name '*.asar' -o -name '*.asar.*' -o -name '*.dmg' -o -name '*.dmg.sha256' -o -name '*.pkg' -o -name '*.pkg.sha256' -o -name '*.zip' -o -name '*.zip.sha256' -o -name '*.tar' -o -name '*.tar.sha256' -o -name '*.tar.gz' -o -name '*.tar.gz.sha256' -o -name '*.tgz' -o -name '*.tgz.sha256' -o -name '*.7z' -o -name '*.7z.sha256' -o -name '*.rar' -o -name '*.rar.sha256' -o -name '*.sqlite' -o -name '*.sqlite-*' -o -name '*.db' -o -name '*.db-*' -o -name '*.log' -o -name 'auth.json' -o -name 'secrets.env' -o \( -name 'config.json' -a -path './ccx/.config/*' \) -o -name '__pycache__' -o -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) \
    -print
  echo "Banned source, runtime, or binary file detected." >&2
  exit 1
fi

echo "== Tracked source payload filenames =="
tracked_payloads="$(git ls-files | grep -E '(^|/)[^/]+\.app(/|$)|\.(app\.sha256|asar|asar\..*|dmg|dmg\.sha256|pkg|pkg\.sha256|zip|zip\.sha256|tar|tar\.sha256|tar\.gz|tar\.gz\.sha256|tgz|tgz\.sha256|7z|7z\.sha256|rar|rar\.sha256|sqlite|sqlite-.*|db|db-.*|log|pyc|pyo)$|(^|/)auth\.json$|(^|/)secrets\.env$|(^|/)__pycache__(/|$)|(^|/)\.DS_Store$|(^|/)ccx/ccx$|(^|/)ccx/\.config/config\.json$' || true)"
if [ -n "${tracked_payloads}" ]; then
  printf '%s\n' "${tracked_payloads}"
  echo "Tracked runtime, binary, cache, or private state file detected." >&2
  exit 1
fi

echo "== High-confidence secret scan =="
SECRET_PATTERNS=(
  'sk-[A-Za-z0-9_-]{20,}'
  'gh[pousr]_[A-Za-z0-9_]{20,}'
  'xox[baprs]-[A-Za-z0-9-]{20,}'
  '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
  'Authorization:[[:space:]]*Bearer[[:space:]]+[A-Za-z0-9._-]{20,}'
  'Cookie:[[:space:]]*[^[:space:]]{20,}'
)

for pattern in "${SECRET_PATTERNS[@]}"; do
  if rg -n --hidden --glob '!.git/**' --glob '!scripts/audit-release.sh' -e "${pattern}" .; then
    echo "Possible secret matched pattern: ${pattern}" >&2
    exit 1
  fi
done

echo "== Local username leak scan =="
current_user="$(id -un 2>/dev/null || true)"
if [ -n "${current_user}" ] && rg -n --hidden --glob '!.git/**' --glob '!scripts/audit-release.sh' -e "/Users/${current_user}" -e "${current_user}" .; then
  echo "Local username or absolute private path detected." >&2
  exit 1
fi

echo "Audit passed."
