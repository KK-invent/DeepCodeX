#!/usr/bin/env python3
"""Import regular Codex conversations into DeepCodeX.

DeepCodeX intentionally runs with its own home directory, usually
~/.codex-deepseek. Regular Codex stores its conversations under ~/.codex. This
tool mirrors the conversation files and the desktop thread index into the
DeepCodeX home so projects started in Codex can be resumed in DeepCodeX.

Only the target DeepCodeX home is written. The source Codex home is read-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


ROLLOUT_RE = re.compile(
    r"^rollout-.*-"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r".*\.jsonl$"
)
MANIFEST_NAME = ".deepcodex-import-manifest.json"
STATE_DB = "state_5.sqlite"
COPY_TREES = ("sessions", "archived_sessions", "shell_snapshots")
STATE_TABLES = ("threads", "thread_dynamic_tools", "thread_spawn_edges")
UNSUPPORTED_THREAD_SOURCES = {"cli"}


def log(msg: str = "") -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def session_uuid(filename: str) -> str | None:
    match = ROLLOUT_RE.match(filename)
    return match.group(1).lower() if match else None


def load_manifest(target_home: Path) -> dict:
    path = target_home / MANIFEST_NAME
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 2, "imported": {}}


def save_manifest(target_home: Path, manifest: dict) -> None:
    path = target_home / MANIFEST_NAME
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def relative_to_or_none(path: Path, root: Path) -> Path | None:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return None


def target_path_for_source(path: Path, source_home: Path, target_home: Path) -> Path | None:
    rel = relative_to_or_none(path, source_home / "sessions")
    if rel is not None:
        return target_home / "sessions" / rel
    rel = relative_to_or_none(path, source_home / "archived_sessions")
    if rel is not None:
        return target_home / "archived_sessions" / rel
    return None


def should_copy(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return True
    src_stat = src.stat()
    dst_stat = dst.stat()
    if dst_stat.st_mtime_ns > src_stat.st_mtime_ns:
        return False
    return src_stat.st_size != dst_stat.st_size or src_stat.st_mtime_ns > dst_stat.st_mtime_ns


def copy_file_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.deepcodex-import.tmp")
    shutil.copy2(src, tmp)
    tmp.replace(dst)


def mirror_tree(source_root: Path, target_root: Path, *, dry_run: bool, verbose: bool) -> tuple[int, int]:
    copied = 0
    skipped = 0
    if not source_root.is_dir():
        return copied, skipped
    for src in sorted(p for p in source_root.rglob("*") if p.is_file()):
        rel = src.relative_to(source_root)
        dst = target_root / rel
        if not should_copy(src, dst):
            skipped += 1
            continue
        copied += 1
        if verbose or dry_run:
            log(f"  copy {source_root.name}/{rel}")
        if not dry_run:
            copy_file_atomic(src, dst)
    return copied, skipped


def mirror_conversation_files(
    source_home: Path,
    target_home: Path,
    *,
    dry_run: bool,
    verbose: bool,
) -> dict[str, int]:
    stats: dict[str, int] = {}
    manifest = load_manifest(target_home)
    imported = manifest.setdefault("imported", {})

    for name in COPY_TREES:
        copied, skipped = mirror_tree(source_home / name, target_home / name, dry_run=dry_run, verbose=verbose)
        stats[f"{name}_copied"] = copied
        stats[f"{name}_skipped"] = skipped

    if not dry_run:
        imported["last_file_sync_at"] = utc_now()
        imported["source_home"] = str(source_home)
        save_manifest(target_home, manifest)
    return stats


def read_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.is_file():
        return records
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                records.append(obj)
    return records


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8")
    tmp.replace(path)


def merge_session_index(
    source_home: Path,
    target_home: Path,
    *,
    dry_run: bool,
    exclude_thread_ids: set[str] | None = None,
) -> tuple[int, int]:
    src = source_home / "session_index.jsonl"
    dst = target_home / "session_index.jsonl"
    excluded = exclude_thread_ids or set()
    source_records = read_jsonl(src)
    target_records = read_jsonl(dst)
    if not source_records and not target_records:
        return (0, 0)

    by_id: dict[str, dict] = {}
    pruned = 0
    for item in target_records:
        sid = item.get("id")
        if not sid:
            continue
        sid = str(sid)
        if sid in excluded:
            pruned += 1
            continue
        by_id[sid] = item

    changed = 0
    for item in source_records:
        sid = item.get("id")
        if not sid:
            continue
        sid = str(sid)
        if sid in excluded:
            continue
        existing = by_id.get(sid)
        if existing is None or str(item.get("updated_at", "")) > str(existing.get("updated_at", "")):
            by_id[sid] = item
            changed += 1

    if (changed or pruned) and not dry_run:
        merged = sorted(by_id.values(), key=lambda item: str(item.get("updated_at", "")))
        write_jsonl(dst, merged)
    return (changed, pruned)


def history_key(obj: dict) -> str:
    raw = json.dumps([obj.get("session_id"), obj.get("ts"), obj.get("text")], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def merge_history(source_home: Path, target_home: Path, *, dry_run: bool, verbose: bool) -> int:
    src = source_home / "history.jsonl"
    dst = target_home / "history.jsonl"
    source_records = read_jsonl(src)
    if not source_records:
        return 0

    target_records = read_jsonl(dst)
    existing = {history_key(item) for item in target_records}
    additions = [item for item in source_records if history_key(item) not in existing]
    if not additions:
        return 0
    if dry_run:
        return len(additions)

    if dst.is_file():
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = dst.with_name(f"history.jsonl.bak.before-import-{stamp}")
        shutil.copy2(dst, backup)
        if verbose:
            log(f"  backed up history -> {backup}")

    write_jsonl(dst, target_records + additions)
    return len(additions)


def connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def connect_rw(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def sqlite_backup(src_path: Path, dst_path: Path) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst_path.with_name(f".{dst_path.name}.tmp")
    if tmp.exists():
        tmp.unlink()
    with connect_ro(src_path) as src, sqlite3.connect(tmp) as dst:
        src.backup(dst)
    tmp.replace(dst_path)


def backup_target_state(target_db: Path) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target_db.with_name(f"state_5.sqlite.bak.before-import-{stamp}")
    sqlite_backup(target_db, backup)
    return backup


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def rewrite_rollout_path(raw_path: str, source_home: Path, target_home: Path) -> str:
    target = target_path_for_source(Path(raw_path), source_home, target_home)
    return str(target) if target is not None else raw_path


def sql_placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))


def load_unsupported_thread_ids(source_home: Path) -> set[str]:
    source_db = source_home / STATE_DB
    if not source_db.is_file():
        return set()
    with connect_ro(source_db) as conn:
        if not table_exists(conn, "threads") or "source" not in columns(conn, "threads"):
            return set()
        placeholders = sql_placeholders(len(UNSUPPORTED_THREAD_SOURCES))
        rows = conn.execute(
            f"SELECT id FROM threads WHERE source IN ({placeholders})",
            sorted(UNSUPPORTED_THREAD_SOURCES),
        ).fetchall()
    return {str(row["id"]) for row in rows}


def count_threads_by_ids(conn: sqlite3.Connection, thread_ids: set[str]) -> int:
    if not thread_ids or not table_exists(conn, "threads"):
        return 0
    placeholders = sql_placeholders(len(thread_ids))
    row = conn.execute(
        f"SELECT count(*) AS n FROM threads WHERE id IN ({placeholders})",
        sorted(thread_ids),
    ).fetchone()
    return int(row["n"] or 0)


def prune_unsupported_thread_state(conn: sqlite3.Connection, thread_ids: set[str]) -> int:
    if not thread_ids:
        return 0
    ids = sorted(thread_ids)
    placeholders = sql_placeholders(len(ids))
    if table_exists(conn, "thread_dynamic_tools"):
        conn.execute(f"DELETE FROM thread_dynamic_tools WHERE thread_id IN ({placeholders})", ids)
    if table_exists(conn, "thread_spawn_edges"):
        conn.execute(
            f"""
            DELETE FROM thread_spawn_edges
            WHERE parent_thread_id IN ({placeholders}) OR child_thread_id IN ({placeholders})
            """,
            ids + ids,
        )
    if not table_exists(conn, "threads"):
        return 0
    cur = conn.execute(f"DELETE FROM threads WHERE id IN ({placeholders})", ids)
    return int(cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0)


def sanitize_seeded_state(
    conn: sqlite3.Connection,
    source_home: Path,
    target_home: Path,
    unsupported_thread_ids: set[str],
) -> tuple[int, int]:
    if table_exists(conn, "remote_control_enrollments"):
        conn.execute("DELETE FROM remote_control_enrollments")
    if table_exists(conn, "agent_job_items"):
        conn.execute("DELETE FROM agent_job_items")
    if table_exists(conn, "agent_jobs"):
        conn.execute("DELETE FROM agent_jobs")

    count = 0
    if table_exists(conn, "threads"):
        rows = conn.execute("SELECT id, rollout_path FROM threads").fetchall()
        for row in rows:
            mapped = rewrite_rollout_path(str(row["rollout_path"]), source_home, target_home)
            conn.execute("UPDATE threads SET rollout_path=? WHERE id=?", (mapped, row["id"]))
            count += 1
    pruned = prune_unsupported_thread_state(conn, unsupported_thread_ids)
    return (count - pruned, pruned)


def upsert_row(conn: sqlite3.Connection, table: str, data: dict) -> None:
    names = list(data)
    placeholders = ", ".join("?" for _ in names)
    quoted = ", ".join(names)
    updates = ", ".join(f"{name}=excluded.{name}" for name in names if name != "id")
    sql = f"INSERT INTO {table} ({quoted}) VALUES ({placeholders})"
    if updates:
        sql += f" ON CONFLICT(id) DO UPDATE SET {updates}"
    conn.execute(sql, [data[name] for name in names])


def insert_or_replace_row(conn: sqlite3.Connection, table: str, data: dict) -> None:
    names = list(data)
    placeholders = ", ".join("?" for _ in names)
    quoted = ", ".join(names)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({quoted}) VALUES ({placeholders})", [data[name] for name in names])


def sync_state_db(
    source_home: Path,
    target_home: Path,
    *,
    dry_run: bool,
    verbose: bool,
    unsupported_thread_ids: set[str] | None = None,
) -> tuple[int, int, int, str | None]:
    source_db = source_home / STATE_DB
    target_db = target_home / STATE_DB
    if not source_db.is_file():
        return (0, 0, 0, None)
    unsupported_thread_ids = unsupported_thread_ids or load_unsupported_thread_ids(source_home)

    if not target_db.exists():
        with connect_ro(source_db) as src:
            source_count = src.execute("SELECT count(*) AS n FROM threads").fetchone()["n"] if table_exists(src, "threads") else 0
            unsupported_count = len(unsupported_thread_ids)
        if dry_run:
            return (max(int(source_count) - unsupported_count, 0), unsupported_count, 0, "seed")
        sqlite_backup(source_db, target_db)
        with connect_rw(target_db) as dst:
            with dst:
                imported, pruned = sanitize_seeded_state(dst, source_home, target_home, unsupported_thread_ids)
        return (imported, 0, pruned, "seed")

    with connect_ro(source_db) as src, connect_rw(target_db) as dst:
        if not table_exists(src, "threads") or not table_exists(dst, "threads"):
            return (0, 0, 0, None)

        src_cols = columns(src, "threads")
        dst_cols = columns(dst, "threads")
        common = [name for name in dst_cols if name in src_cols]
        source_rows = src.execute("SELECT * FROM threads").fetchall()
        target_updated = {
            str(row["id"]): int(row["updated_at"] or 0)
            for row in dst.execute("SELECT id, updated_at FROM threads").fetchall()
        }

        thread_rows: list[dict] = []
        skipped = 0
        for row in source_rows:
            thread_id = str(row["id"])
            # 旧终端版 Codex 会话当前会让桌面端打开后卡黑屏；先只同步文件，不放进 UI 索引。
            if thread_id in unsupported_thread_ids:
                skipped += 1
                continue
            source_updated = int(row["updated_at"] or 0)
            if thread_id in target_updated and target_updated[thread_id] >= source_updated:
                skipped += 1
                continue
            data = {name: row[name] for name in common}
            if "rollout_path" in data:
                data["rollout_path"] = rewrite_rollout_path(str(data["rollout_path"]), source_home, target_home)
            thread_rows.append(data)

        target_prune_count = count_threads_by_ids(dst, unsupported_thread_ids)
        if not thread_rows and not target_prune_count:
            return (0, skipped, 0, None)
        if dry_run:
            return (len(thread_rows), skipped, target_prune_count, None)

        backup = backup_target_state(target_db)
        if verbose:
            log(f"  backed up state -> {backup}")

        changed_ids = [str(row["id"]) for row in thread_rows]
        with dst:
            pruned = prune_unsupported_thread_state(dst, unsupported_thread_ids)
            for data in thread_rows:
                upsert_row(dst, "threads", data)

            if table_exists(src, "thread_dynamic_tools") and table_exists(dst, "thread_dynamic_tools"):
                src_tool_cols = columns(src, "thread_dynamic_tools")
                dst_tool_cols = columns(dst, "thread_dynamic_tools")
                tool_common = [name for name in dst_tool_cols if name in src_tool_cols]
                for thread_id in changed_ids:
                    dst.execute("DELETE FROM thread_dynamic_tools WHERE thread_id=?", (thread_id,))
                    for row in src.execute("SELECT * FROM thread_dynamic_tools WHERE thread_id=?", (thread_id,)).fetchall():
                        insert_or_replace_row(dst, "thread_dynamic_tools", {name: row[name] for name in tool_common})

            if table_exists(src, "thread_spawn_edges") and table_exists(dst, "thread_spawn_edges"):
                src_edge_cols = columns(src, "thread_spawn_edges")
                dst_edge_cols = columns(dst, "thread_spawn_edges")
                edge_common = [name for name in dst_edge_cols if name in src_edge_cols]
                for row in src.execute("SELECT * FROM thread_spawn_edges").fetchall():
                    parent_id = str(row["parent_thread_id"]) if "parent_thread_id" in src_edge_cols else ""
                    child_id = str(row["child_thread_id"]) if "child_thread_id" in src_edge_cols else ""
                    if parent_id in unsupported_thread_ids or child_id in unsupported_thread_ids:
                        continue
                    insert_or_replace_row(dst, "thread_spawn_edges", {name: row[name] for name in edge_common})

        return (len(thread_rows), skipped, pruned, None)


def write_summary_manifest(target_home: Path, summary: dict, *, dry_run: bool) -> None:
    if dry_run:
        return
    manifest = load_manifest(target_home)
    manifest["version"] = 2
    manifest["last_run"] = utc_now()
    manifest["last_summary"] = summary
    save_manifest(target_home, manifest)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deepcodex-session-import.py",
        description="Import regular Codex conversations into DeepCodeX so they can be resumed there.",
    )
    parser.add_argument("--source", default=os.environ.get("CODEX_SOURCE_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--target", default=os.environ.get("DEEPCODEX_HOME", str(Path.home() / ".codex-deepseek")))
    parser.add_argument("--include-history", action="store_true", help="Also merge history.jsonl.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be imported without writing.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed import actions.")
    parser.add_argument("--selftest", action="store_true", help="Run an isolated self-test.")
    return parser.parse_args(argv)


def run_import(args: argparse.Namespace) -> int:
    source_home = Path(args.source).expanduser()
    target_home = Path(args.target).expanduser()

    if source_home.resolve() == target_home.resolve():
        log("ERROR: --source and --target are the same home; nothing to do.")
        return 2
    if not source_home.is_dir():
        log(f"source home not found: {source_home} - nothing to import.")
        return 0
    if not target_home.is_dir() and not args.dry_run:
        target_home.mkdir(parents=True, exist_ok=True)

    mode = "DRY RUN" if args.dry_run else "IMPORT"
    log(f"DeepCodeX session import [{mode}]")
    log(f"  source: {source_home}")
    log(f"  target: {target_home}")
    log("")

    unsupported_thread_ids = load_unsupported_thread_ids(source_home)
    summary = mirror_conversation_files(source_home, target_home, dry_run=args.dry_run, verbose=args.verbose)
    index_changed, index_pruned = merge_session_index(
        source_home,
        target_home,
        dry_run=args.dry_run,
        exclude_thread_ids=unsupported_thread_ids,
    )
    state_imported, state_skipped, state_pruned, state_mode = sync_state_db(
        source_home,
        target_home,
        dry_run=args.dry_run,
        verbose=args.verbose,
        unsupported_thread_ids=unsupported_thread_ids,
    )
    history_added = 0
    if args.include_history:
        history_added = merge_history(source_home, target_home, dry_run=args.dry_run, verbose=args.verbose)

    summary.update(
        {
            "session_index_changed": index_changed,
            "session_index_pruned": index_pruned,
            "state_threads_imported": state_imported,
            "state_threads_skipped": state_skipped,
            "state_threads_pruned": state_pruned,
            "state_mode": state_mode,
            "unsupported_cli_threads": len(unsupported_thread_ids),
            "history_added": history_added,
        }
    )
    write_summary_manifest(target_home, summary, dry_run=args.dry_run)

    verb = "would import" if args.dry_run else "imported"
    log(f"Sessions: {verb} {summary['sessions_copied']}, skipped {summary['sessions_skipped']}.")
    log(f"Archived: {verb} {summary['archived_sessions_copied']}, skipped {summary['archived_sessions_skipped']}.")
    log(f"Shell snapshots: {verb} {summary['shell_snapshots_copied']}, skipped {summary['shell_snapshots_skipped']}.")
    log(f"Session index: {'would update' if args.dry_run else 'updated'} {index_changed} records.")
    if index_pruned:
        log(f"Session index: {'would prune' if args.dry_run else 'pruned'} {index_pruned} unsupported CLI records.")
    log(f"State index: {verb} {state_imported} threads, skipped {state_skipped}, pruned {state_pruned}.")
    if unsupported_thread_ids:
        log(f"Legacy CLI sessions: kept {len(unsupported_thread_ids)} records out of the DeepCodeX UI index.")
    if args.include_history:
        log(f"History: {'would add' if args.dry_run else 'added'} {history_added} entries.")
    return 0


def create_test_state_db(path: Path, rollout_path: Path, thread_id: str, updated_at: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                rollout_path TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                source TEXT NOT NULL,
                model_provider TEXT NOT NULL,
                cwd TEXT NOT NULL,
                title TEXT NOT NULL,
                sandbox_policy TEXT NOT NULL,
                approval_mode TEXT NOT NULL,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                has_user_event INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                archived_at INTEGER,
                preview TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE thread_dynamic_tools (
                thread_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                input_schema TEXT NOT NULL,
                PRIMARY KEY(thread_id, position)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE thread_spawn_edges (
                parent_thread_id TEXT NOT NULL,
                child_thread_id TEXT NOT NULL PRIMARY KEY,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO threads (
                id, rollout_path, created_at, updated_at, source, model_provider, cwd,
                title, sandbox_policy, approval_mode, preview
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                str(rollout_path),
                updated_at - 10,
                updated_at,
                "vscode",
                "openai",
                "/tmp/project",
                "Codex project",
                "danger-full-access",
                "never",
                "hello",
            ),
        )
        conn.execute(
            "INSERT INTO thread_dynamic_tools VALUES (?, ?, ?, ?, ?)",
            (thread_id, 0, "tool", "desc", "{}"),
        )


def selftest() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source"
        target = root / "target"
        sid = "019e8aaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"
        legacy_sid = "019e8bbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb"
        source_rollout = source / "sessions/2026/06/01" / f"rollout-2026-06-01T00-00-00-{sid}.jsonl"
        legacy_rollout = source / "sessions/2026/06/01" / f"rollout-2026-06-01T00-00-00-{legacy_sid}.jsonl"
        source_rollout.parent.mkdir(parents=True)
        source_rollout.write_text('{"type":"session_meta","payload":{"id":"' + sid + '"}}\n', encoding="utf-8")
        legacy_rollout.write_text('{"type":"session_meta","payload":{"id":"' + legacy_sid + '"}}\n', encoding="utf-8")
        (source / "archived_sessions").mkdir(parents=True)
        (source / "archived_sessions" / f"rollout-2026-05-01T00-00-00-{sid}.jsonl").write_text("archived\n", encoding="utf-8")
        (source / "shell_snapshots").mkdir(parents=True)
        (source / "shell_snapshots" / f"{sid}.1.sh").write_text("pwd\n", encoding="utf-8")
        (target / "sessions").mkdir(parents=True)
        (source / "session_index.jsonl").write_text(
            json.dumps({"id": sid, "thread_name": "Codex project", "updated_at": "2026-06-01T00:00:00Z"}) + "\n"
            + json.dumps({"id": legacy_sid, "thread_name": "Legacy CLI", "updated_at": "2026-06-01T00:00:01Z"}) + "\n",
            encoding="utf-8",
        )
        (source / "history.jsonl").write_text(json.dumps({"session_id": sid, "ts": 1, "text": "hello"}) + "\n", encoding="utf-8")
        create_test_state_db(source / STATE_DB, source_rollout, sid, 100)
        with sqlite3.connect(source / STATE_DB) as conn:
            conn.execute(
                """
                INSERT INTO threads (
                    id, rollout_path, created_at, updated_at, source, model_provider, cwd,
                    title, sandbox_policy, approval_mode, preview
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    legacy_sid,
                    str(legacy_rollout),
                    90,
                    101,
                    "cli",
                    "openai",
                    "/tmp/project",
                    "Legacy CLI",
                    "danger-full-access",
                    "never",
                    "legacy",
                ),
            )
            conn.execute(
                "INSERT INTO thread_dynamic_tools VALUES (?, ?, ?, ?, ?)",
                (legacy_sid, 0, "legacy-tool", "desc", "{}"),
            )

        args = argparse.Namespace(
            source=str(source),
            target=str(target),
            include_history=True,
            dry_run=False,
            verbose=False,
        )
        rc = run_import(args)
        if rc != 0:
            raise AssertionError(f"import rc={rc}")
        copied = target / "sessions/2026/06/01" / source_rollout.name
        if not copied.is_file():
            raise AssertionError("session rollout was not copied")
        if not (target / "archived_sessions" / f"rollout-2026-05-01T00-00-00-{sid}.jsonl").is_file():
            raise AssertionError("archived rollout was not copied")
        with sqlite3.connect(target / STATE_DB) as conn:
            row = conn.execute("SELECT rollout_path FROM threads WHERE id=?", (sid,)).fetchone()
        if row is None or row[0] != str(copied):
            raise AssertionError("thread state was not imported with rewritten rollout path")
        with sqlite3.connect(target / STATE_DB) as conn:
            legacy_row = conn.execute("SELECT id FROM threads WHERE id=?", (legacy_sid,)).fetchone()
            legacy_tool = conn.execute("SELECT thread_id FROM thread_dynamic_tools WHERE thread_id=?", (legacy_sid,)).fetchone()
        if legacy_row is not None or legacy_tool is not None:
            raise AssertionError("legacy CLI thread state was imported into the UI index")
        if not (target / "session_index.jsonl").is_file():
            raise AssertionError("session index was not written")
        if legacy_sid in (target / "session_index.jsonl").read_text(encoding="utf-8"):
            raise AssertionError("legacy CLI thread was written to the session index")
        if not (target / "history.jsonl").is_file():
            raise AssertionError("history was not merged")
    log("session import selftest OK")
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest()
    return run_import(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
