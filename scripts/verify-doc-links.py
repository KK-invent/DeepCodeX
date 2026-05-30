#!/usr/bin/env python3
"""Verify local Markdown links and image assets before release."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path


INLINE_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_IMAGE_RE = re.compile(r"<img\s+[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
SKIP_DIRS = {".git", ".omc", "dist", "release-work"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan. Defaults to the current directory.",
    )
    return parser.parse_args()


def markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return sorted(files)


def local_target(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if value.startswith("<") and ">" in value:
        value = value[1 : value.index(">")]
    else:
        value = value.split()[0]
    if value.startswith(("#", "http://", "https://", "mailto:", "tel:")):
        return None
    path = urllib.parse.unquote(value.split("#", 1)[0])
    return path or None


def in_repo(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    failures: list[tuple[Path, str]] = []
    checked_links = 0

    for doc in markdown_files(root):
        text = doc.read_text(encoding="utf-8")
        raw_links = [match.group(1) for match in INLINE_LINK_RE.finditer(text)]
        raw_links.extend(match.group(1) for match in HTML_IMAGE_RE.finditer(text))

        for raw in raw_links:
            target = local_target(raw)
            if target is None:
                continue
            checked_links += 1
            resolved = (doc.parent / target).resolve()
            if in_repo(resolved, root) and not resolved.exists():
                failures.append((doc.relative_to(root), raw))

    if failures:
        print("Missing local Markdown links or assets:", file=sys.stderr)
        for doc, raw in failures:
            print(f"  {doc}: {raw}", file=sys.stderr)
        return 1

    print(
        f"Checked {len(markdown_files(root))} Markdown files and {checked_links} local links/assets."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
