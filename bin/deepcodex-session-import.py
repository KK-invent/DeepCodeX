#!/usr/bin/env python3
"""deepcodex-session-import.py — import Codex conversations into DeepCodeX.

DeepCodeX runs with its own isolated home (``~/.codex-deepseek``) so it never
pollutes a normal Codex install. The side effect is that DeepCodeX cannot see
the conversations created by the regular Codex app: those live under the normal
``~/.codex`` home. This tool mirrors the regular Codex session rollouts (and,
optionally, the cross-session message history) into the DeepCodeX home so that
every past Codex conversation shows up in DeepCodeX's resume/history picker and
a project can be continued seamlessly.

Design goals:
  * **Safe.** Only ever writes inside the *target* DeepCodeX home data directory
    (sessions/, history.jsonl, a sidecar manifest). It never touches the app
    bundle, app.asar, the bridge, the image shim, or the request chain. The
    source home is opened read-only.
  * **Idempotent.** Re-running only imports rollouts that are not already
    present in the target (deduplicated by the session UUID embedded in the
    rollout filename). A sidecar manifest records what was imported so repeat
    runs are fast and report only what is new.
  * **Reversible.** ``--include-history`` backs up the target history.jsonl
    before merging, and prints the backup path.

Typical use:
    # preview what would be imported (writes nothing)
    deepcodex-session-import.py --dry-run

    # import session rollouts (the conversations) only
    deepcodex-session-import.py

    # also merge the cross-session message history
    deepcodex-session-import.py --include-history

Defaults:
    --source  $CODEX_SOURCE_HOME or ~/.codex            (the regular Codex home)
    --target  $DEEPCODEX_HOME or ~/.codex-deepseek      (the DeepCodeX home)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

# A Codex rollout file is named:
#   rollout-<ISO-timestamp>-<session-uuid>.jsonl
# and lives under sessions/YYYY/MM/DD/. The UUID is the stable identity we use
# to deduplicate; the timestamp can collide across homes but the UUID will not.
ROLLOUT_RE = re.compile(
    r"^rollout-.*-"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{0,12})"
    r".*\.jsonl$"
)

MANIFEST_NAME = ".deepcodex-import-manifest.json"


def log(msg: str = "") -> None:
    print(msg, flush=True)


def session_uuid(filename: str) -> str | None:
    """Extract the session UUID from a rollout filename, or None."""
    m = ROLLOUT_RE.match(filename)
    return m.group(1).lower() if m else None


def find_rollouts(sessions_root: Path) -> dict[str, Path]:
    """Map session-uuid -> rollout path for every rollout under sessions_root.

    If two rollouts share a UUID (should not happen), the lexicographically
    last path wins; this keeps the scan deterministic.
    """
    found: dict[str, Path] = {}
    if not sessions_root.is_dir():
        return found
    for path in sorted(sessions_root.rglob("rollout-*.jsonl")):
        uid = session_uuid(path.name)
        if uid:
            found[uid] = path
    return found


def load_manifest(target_home: Path) -> dict:
    path = target_home / MANIFEST_NAME
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "imported": {}}


def save_manifest(target_home: Path, manifest: dict) -> None:
    path = target_home / MANIFEST_NAME
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def import_sessions(
    source_home: Path,
    target_home: Path,
    *,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int]:
    """Mirror source rollouts into the target home. Returns (imported, skipped)."""
    source_sessions = source_home / "sessions"
    target_sessions = target_home / "sessions"

    source = find_rollouts(source_sessions)
    target = find_rollouts(target_sessions)

    if not source:
        log(f"No rollouts found under {source_sessions} — nothing to import.")
        return (0, 0)

    manifest = load_manifest(target_home)
    imported_map = manifest.setdefault("imported", {})

    imported = 0
    skipped = 0
    for uid, src_path in source.items():
        if uid in target or uid in imported_map:
            skipped += 1
            if verbose:
                log(f"  skip  {uid}  (already present)")
            continue

        # Preserve the YYYY/MM/DD/ layout relative to the sessions root.
        rel = src_path.relative_to(source_sessions)
        dst_path = target_sessions / rel

        if verbose or dry_run:
            log(f"  import {uid}  {rel}")

        if not dry_run:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            imported_map[uid] = {
                "source": str(src_path),
                "target": str(dst_path),
                "imported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
        imported += 1

    if not dry_run and imported:
        manifest["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        save_manifest(target_home, manifest)

    return (imported, skipped)


def _history_key(obj: dict) -> str:
    """Stable dedup key for a history.jsonl entry."""
    raw = json.dumps(
        [obj.get("session_id"), obj.get("ts"), obj.get("text")],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def merge_history(
    source_home: Path,
    target_home: Path,
    *,
    dry_run: bool,
    verbose: bool,
) -> int:
    """Append source history entries not already in the target. Returns count added."""
    src = source_home / "history.jsonl"
    dst = target_home / "history.jsonl"

    if not src.is_file():
        log(f"No history.jsonl at {src} — skipping history merge.")
        return 0

    existing: set[str] = set()
    dst_lines: list[str] = []
    if dst.is_file():
        with dst.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                dst_lines.append(line)
                try:
                    existing.add(_history_key(json.loads(line)))
                except json.JSONDecodeError:
                    continue

    additions: list[str] = []
    with src.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = _history_key(obj)
            if key in existing:
                continue
            existing.add(key)
            additions.append(json.dumps(obj, ensure_ascii=False))

    if not additions:
        log("History already in sync — no new entries.")
        return 0

    if dry_run:
        log(f"  would add {len(additions)} history entries to {dst}")
        return len(additions)

    # Back up the target history before mutating it.
    if dst.is_file():
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = dst.with_name(f"history.jsonl.bak.before-import-{stamp}")
        shutil.copy2(dst, backup)
        log(f"  backed up history -> {backup}")

    merged = dst_lines + additions
    tmp = dst.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(merged) + "\n", encoding="utf-8")
    tmp.replace(dst)
    if verbose:
        log(f"  appended {len(additions)} entries to {dst}")
    return len(additions)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="deepcodex-session-import.py",
        description="Import regular Codex conversations into DeepCodeX so they "
        "can be resumed and continued there.",
    )
    default_target = os.environ.get(
        "DEEPCODEX_HOME", str(Path.home() / ".codex-deepseek")
    )
    default_source = os.environ.get("CODEX_SOURCE_HOME", str(Path.home() / ".codex"))
    p.add_argument(
        "--source",
        default=default_source,
        help="Regular Codex home to read from (default: $CODEX_SOURCE_HOME or ~/.codex).",
    )
    p.add_argument(
        "--target",
        default=default_target,
        help="DeepCodeX home to write into (default: $DEEPCODEX_HOME or ~/.codex-deepseek).",
    )
    p.add_argument(
        "--include-history",
        action="store_true",
        help="Also merge the cross-session history.jsonl (backed up first).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be imported without writing anything.",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print each session as it is considered.",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    source_home = Path(args.source).expanduser()
    target_home = Path(args.target).expanduser()

    if source_home.resolve() == target_home.resolve():
        log("ERROR: --source and --target are the same home; nothing to do.")
        return 2
    if not source_home.is_dir():
        log(f"source home not found: {source_home} — nothing to import.")
        return 0
    if not target_home.is_dir():
        log(f"ERROR: target home not found: {target_home}")
        return 2

    mode = "DRY RUN" if args.dry_run else "IMPORT"
    log(f"DeepCodeX session import [{mode}]")
    log(f"  source: {source_home}")
    log(f"  target: {target_home}")
    log("")

    imported, skipped = import_sessions(
        source_home, target_home, dry_run=args.dry_run, verbose=args.verbose
    )
    log("")
    verb = "would import" if args.dry_run else "imported"
    log(f"Sessions: {verb} {imported}, skipped {skipped} (already present).")

    if args.include_history:
        log("")
        added = merge_history(
            source_home, target_home, dry_run=args.dry_run, verbose=args.verbose
        )
        verb = "would add" if args.dry_run else "added"
        log(f"History: {verb} {added} entries.")

    if not args.dry_run and imported:
        log("")
        log("Done. Restart DeepCodeX (or reopen the history picker) to see the "
            "imported conversations.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
