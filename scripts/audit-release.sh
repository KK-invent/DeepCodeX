#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

echo "== Python syntax =="
python3 -m py_compile bin/*.py

echo "== Image-strip self-test =="
python3 bin/deepcodex-image-strip-proxy.py --selftest

echo "== Banned tracked/runtime filenames =="
if find . \
  -path ./.git -prune -o \
  \( -name '*.app' -o -name '*.asar' -o -name '*.dmg' -o -name '*.pkg' -o -name '*.sqlite' -o -name '*.db' -o -name '*.log' -o -name 'auth.json' -o -name 'secrets.env' -o -name 'config.json' -path './ccx/.config/*' \) \
  -print | grep -q .; then
  find . \
    -path ./.git -prune -o \
    \( -name '*.app' -o -name '*.asar' -o -name '*.dmg' -o -name '*.pkg' -o -name '*.sqlite' -o -name '*.db' -o -name '*.log' -o -name 'auth.json' -o -name 'secrets.env' -o -name 'config.json' -path './ccx/.config/*' \) \
    -print
  echo "Banned runtime or binary file detected." >&2
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
if rg -n --hidden --glob '!.git/**' --glob '!scripts/audit-release.sh' '/Users/zhaozimin|zhaozimin' .; then
  echo "Local username or absolute private path detected." >&2
  exit 1
fi

echo "Audit passed."
