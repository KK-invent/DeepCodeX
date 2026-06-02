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
import uuid
from pathlib import Path


ROLLOUT_RE = re.compile(
    r"^rollout-.*-"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r".*\.jsonl$"
)
MANIFEST_NAME = ".deepcodex-import-manifest.json"
GLOBAL_STATE_NAME = ".codex-global-state.json"
STATE_DB = "state_5.sqlite"
COPY_TREES = ("sessions", "archived_sessions", "shell_snapshots")
STATE_TABLES = ("threads", "thread_dynamic_tools", "thread_spawn_edges")
LEGACY_CLI_THREAD_SOURCES = {"cli"}
DEEPCODEX_MODEL_PROVIDER = "ccx-deepseek"
DEEPCODEX_DEFAULT_MODEL = "deepseek-v4-flash"
SIDEBAR_STATE_KEYS = (
    "project-order",
    "projectless-thread-ids",
    "thread-workspace-root-hints",
    "thread-projectless-output-directories",
    "pinned-thread-ids",
    "electron-saved-workspace-roots",
    "active-workspace-roots",
)


def log(msg: str = "") -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def iso_from_epoch(raw: object) -> str:
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return utc_now()
    return _dt.datetime.fromtimestamp(value, _dt.timezone.utc).isoformat().replace("+00:00", "Z")


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
    tmp = dst.with_name(f".{dst.name}.deepcodex-import.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    shutil.copy2(src, tmp)
    tmp.replace(dst)


def write_text_atomic(dst: Path, content: str, *, source_stat: os.stat_result | None = None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.deepcodex-import.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dst)
    if source_stat is not None:
        os.utime(dst, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))


def normalize_deepcodex_model(raw: object) -> object:
    if not isinstance(raw, str) or not raw:
        return raw
    if raw.startswith("deepseek-v4-"):
        return raw
    return DEEPCODEX_DEFAULT_MODEL


def normalize_imported_rollout_record(obj: dict) -> dict:
    normalized = dict(obj)
    payload = normalized.get("payload")
    if not isinstance(payload, dict):
        return normalized

    payload = dict(payload)
    record_type = normalized.get("type")
    if record_type == "session_meta":
        # DeepCodeX 的服务端会读取 rollout 文件头来决定该 thread 属于哪个 provider。
        # 只改元数据，不改历史消息正文。
        payload["model_provider"] = DEEPCODEX_MODEL_PROVIDER
        if "model" in payload:
            payload["model"] = normalize_deepcodex_model(payload.get("model"))
    elif record_type == "turn_context" and "model" in payload:
        payload["model"] = normalize_deepcodex_model(payload.get("model"))

    normalized["payload"] = payload
    return normalized


def normalized_imported_rollout_content(src: Path) -> str | None:
    if src.suffix != ".jsonl":
        return None
    records: list[str] = []
    try:
        with src.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    records.append(line)
                    continue
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    return None
                records.append(json.dumps(normalize_imported_rollout_record(obj), ensure_ascii=False) + "\n")
    except (OSError, json.JSONDecodeError):
        return None
    return "".join(records)


def mirror_tree(
    source_root: Path,
    target_root: Path,
    *,
    dry_run: bool,
    verbose: bool,
    normalize_rollouts: bool = False,
    skip_thread_ids: set[str] | None = None,
) -> tuple[int, int]:
    copied = 0
    skipped = 0
    skip_thread_ids = skip_thread_ids or set()
    if not source_root.is_dir():
        return copied, skipped
    for src in sorted(p for p in source_root.rglob("*") if p.is_file()):
        rel = src.relative_to(source_root)
        if session_uuid(src.name) in skip_thread_ids:
            skipped += 1
            continue
        dst = target_root / rel
        normalized_content = normalized_imported_rollout_content(src) if normalize_rollouts else None
        if normalized_content is not None:
            if dst.exists():
                try:
                    if dst.read_text(encoding="utf-8") == normalized_content:
                        if not dry_run:
                            src_stat = src.stat()
                            try:
                                dst_stat = dst.stat()
                            except OSError:
                                dst_stat = None
                            if dst_stat is None or dst_stat.st_mtime_ns != src_stat.st_mtime_ns:
                                os.utime(dst, ns=(src_stat.st_atime_ns, src_stat.st_mtime_ns))
                        skipped += 1
                        continue
                except OSError:
                    pass
            copied += 1
            if verbose or dry_run:
                log(f"  copy {source_root.name}/{rel}")
            if not dry_run:
                write_text_atomic(dst, normalized_content, source_stat=src.stat())
            continue
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
    legacy_cli_ids: set[str] | None = None,
) -> dict[str, int]:
    stats: dict[str, int] = {}
    manifest = load_manifest(target_home)
    imported = manifest.setdefault("imported", {})

    for name in COPY_TREES:
        copied, skipped = mirror_tree(
            source_home / name,
            target_home / name,
            dry_run=dry_run,
            verbose=verbose,
            normalize_rollouts=name in {"sessions", "archived_sessions"},
            skip_thread_ids=legacy_cli_ids if name == "sessions" else None,
        )
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
    extra_records: list[dict] | None = None,
) -> tuple[int, int]:
    src = source_home / "session_index.jsonl"
    dst = target_home / "session_index.jsonl"
    source_records = read_jsonl(src) + (extra_records or [])
    target_records = read_jsonl(dst)
    if not source_records and not target_records:
        return (0, 0)

    by_id: dict[str, dict] = {}
    for item in target_records:
        sid = item.get("id")
        if not sid:
            continue
        sid = str(sid)
        by_id[sid] = item

    changed = 0
    for item in source_records:
        sid = item.get("id")
        if not sid:
            continue
        sid = str(sid)
        existing = by_id.get(sid)
        if existing is None or str(item.get("updated_at", "")) > str(existing.get("updated_at", "")):
            by_id[sid] = item
            changed += 1

    if changed and not dry_run:
        merged = sorted(by_id.values(), key=lambda item: str(item.get("updated_at", "")))
        write_jsonl(dst, merged)
    return (changed, 0)


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


def load_legacy_cli_thread_rows(source_home: Path) -> dict[str, dict]:
    source_db = source_home / STATE_DB
    if not source_db.is_file():
        return {}
    with connect_ro(source_db) as conn:
        if not table_exists(conn, "threads") or "source" not in columns(conn, "threads"):
            return {}
        placeholders = sql_placeholders(len(LEGACY_CLI_THREAD_SOURCES))
        rows = conn.execute(
            f"SELECT * FROM threads WHERE source IN ({placeholders})",
            sorted(LEGACY_CLI_THREAD_SOURCES),
        ).fetchall()
    return {str(row["id"]): dict(row) for row in rows}


def legacy_cli_session_index_records(rows: dict[str, dict]) -> list[dict]:
    records: list[dict] = []
    for thread_id, row in rows.items():
        records.append(
            {
                "id": thread_id,
                "thread_name": row.get("title") or row.get("first_user_message") or thread_id,
                "updated_at": iso_from_epoch(row.get("updated_at")),
            }
        )
    return records


def load_global_state(target_home: Path) -> dict:
    path = target_home / GLOBAL_STATE_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_global_state(target_home: Path, data: dict) -> None:
    path = target_home / GLOBAL_STATE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def stable_list_key(item: object) -> str:
    try:
        return json.dumps(item, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(item)


def merge_unique_list(source: list, target: object) -> list:
    existing = target if isinstance(target, list) else []
    merged: list = []
    seen: set[str] = set()
    for item in [*source, *existing]:
        key = stable_list_key(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def merge_sidebar_value(source_value: object, target_value: object) -> object:
    if isinstance(source_value, list):
        return merge_unique_list(source_value, target_value)
    if isinstance(source_value, dict):
        merged = dict(target_value) if isinstance(target_value, dict) else {}
        # Codex 侧的同 ID 映射优先，DeepCodex 独有项保留。
        merged.update(source_value)
        return merged
    return source_value


def projectless_thread_ids(state: dict) -> set[str]:
    ids = state.get("projectless-thread-ids")
    return {str(item) for item in ids} if isinstance(ids, list) else set()


def sync_sidebar_state(source_home: Path, target_home: Path, *, dry_run: bool) -> dict[str, int]:
    source_state = load_global_state(source_home)
    if not source_state:
        return {
            "keys_changed": 0,
            "codex_projectless_threads": 0,
            "total_projectless_threads": 0,
            "codex_projects": 0,
            "total_projects": 0,
        }

    target_state = load_global_state(target_home)
    changed = 0
    for key in SIDEBAR_STATE_KEYS:
        if key not in source_state:
            continue
        source_value = source_state[key]
        if key == "thread-workspace-root-hints" and isinstance(source_value, dict):
            source_value = dict(source_value)
            # Codex 的 projectless 对话在 DeepCodeX 里必须继续保持 projectless，
            # 否则左侧“对话”区会把它们当项目/root 线程过滤掉。
            for thread_id in projectless_thread_ids(source_state):
                source_value[thread_id] = "~"
        merged = merge_sidebar_value(source_value, target_state.get(key))
        if target_state.get(key) != merged:
            target_state[key] = merged
            changed += 1

    if changed and not dry_run:
        write_global_state(target_home, target_state)

    source_projectless = source_state.get("projectless-thread-ids")
    target_projectless = target_state.get("projectless-thread-ids")
    source_projects = source_state.get("project-order")
    target_projects = target_state.get("project-order")
    return {
        "keys_changed": changed,
        "codex_projectless_threads": len(source_projectless) if isinstance(source_projectless, list) else 0,
        "total_projectless_threads": len(target_projectless) if isinstance(target_projectless, list) else 0,
        "codex_projects": len(source_projects) if isinstance(source_projects, list) else 0,
        "total_projects": len(target_projects) if isinstance(target_projects, list) else 0,
    }


def parse_sandbox_policy(raw: object) -> object:
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def normalize_legacy_cli_record(obj: dict, row: dict) -> dict:
    normalized = dict(obj)
    payload = normalized.get("payload")
    if not isinstance(payload, dict):
        return normalized

    payload = dict(payload)
    if normalized.get("type") == "session_meta":
        payload["originator"] = "Codex Desktop"
        payload["source"] = "vscode"
        payload["thread_source"] = payload.get("thread_source") or row.get("thread_source") or "user"
        payload["cwd"] = row.get("cwd") or payload.get("cwd")
        payload["model_provider"] = row.get("model_provider") or payload.get("model_provider")
    elif normalized.get("type") == "turn_context":
        payload["cwd"] = row.get("cwd") or payload.get("cwd")
        payload["approval_policy"] = row.get("approval_mode") or payload.get("approval_policy")
        payload["sandbox_policy"] = parse_sandbox_policy(row.get("sandbox_policy")) or payload.get("sandbox_policy")
        payload["permission_profile"] = {"type": "disabled"}
        payload["model"] = row.get("model") or payload.get("model")
        payload.setdefault("personality", "pragmatic")
        payload.setdefault("realtime_active", False)

    normalized["payload"] = payload
    return normalized


def legacy_cli_target_path(row: dict, source_home: Path, target_home: Path) -> Path | None:
    raw = row.get("rollout_path")
    if not raw:
        return None
    return target_path_for_source(Path(str(raw)), source_home, target_home)


def convert_legacy_cli_rollouts(
    source_home: Path,
    target_home: Path,
    rows: dict[str, dict],
    *,
    dry_run: bool,
    verbose: bool,
) -> int:
    converted = 0
    for thread_id, row in sorted(rows.items()):
        raw_path = row.get("rollout_path")
        if not raw_path:
            continue
        src = Path(str(raw_path))
        dst = legacy_cli_target_path(row, source_home, target_home)
        if dst is None or not src.is_file():
            continue
        records = [normalize_legacy_cli_record(item, row) for item in read_jsonl(src)]
        content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records)
        if dst.is_file() and dst.read_text(encoding="utf-8") == content:
            continue
        converted += 1
        if verbose or dry_run:
            rel = relative_to_or_none(dst, target_home)
            log(f"  convert legacy-cli {rel or dst}")
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(f".{dst.name}.deepcodex-legacy-cli.tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(dst)
    return converted


def normalize_legacy_cli_thread_data(data: dict, row: dict, source_home: Path, target_home: Path) -> dict:
    normalized = dict(data)
    target = legacy_cli_target_path(row, source_home, target_home)
    if target is not None:
        normalized["rollout_path"] = str(target)
    normalized["source"] = "vscode"
    if "model_provider" in normalized:
        normalized["model_provider"] = DEEPCODEX_MODEL_PROVIDER
    if "model" in normalized:
        normalized["model"] = normalize_deepcodex_model(normalized.get("model"))
    if "thread_source" in normalized:
        normalized["thread_source"] = normalized.get("thread_source") or "user"
    return normalized


def normalize_imported_thread_data(data: dict, source_home: Path, target_home: Path) -> dict:
    normalized = dict(data)
    if "rollout_path" in normalized:
        normalized["rollout_path"] = rewrite_rollout_path(str(normalized["rollout_path"]), source_home, target_home)
    if "model_provider" in normalized:
        normalized["model_provider"] = DEEPCODEX_MODEL_PROVIDER
    if "model" in normalized:
        normalized["model"] = normalize_deepcodex_model(normalized.get("model"))
    return normalized


def sanitize_seeded_state(
    conn: sqlite3.Connection,
    source_home: Path,
    target_home: Path,
    legacy_cli_rows: dict[str, dict],
) -> int:
    if table_exists(conn, "remote_control_enrollments"):
        conn.execute("DELETE FROM remote_control_enrollments")
    if table_exists(conn, "agent_job_items"):
        conn.execute("DELETE FROM agent_job_items")
    if table_exists(conn, "agent_jobs"):
        conn.execute("DELETE FROM agent_jobs")

    count = 0
    if table_exists(conn, "threads"):
        rows = conn.execute("SELECT id, rollout_path FROM threads").fetchall()
        thread_cols = columns(conn, "threads")
        for row in rows:
            mapped = rewrite_rollout_path(str(row["rollout_path"]), source_home, target_home)
            source = "vscode" if str(row["id"]) in legacy_cli_rows else None
            provider_sql = ", model_provider=?" if "model_provider" in thread_cols else ""
            model_sql = ", model=?" if "model" in thread_cols else ""
            if source is None:
                values = [mapped]
                if provider_sql:
                    values.append(DEEPCODEX_MODEL_PROVIDER)
                if model_sql:
                    values.append(DEEPCODEX_DEFAULT_MODEL)
                values.append(row["id"])
                conn.execute(f"UPDATE threads SET rollout_path=?{provider_sql}{model_sql} WHERE id=?", values)
            else:
                values = [mapped, source]
                if provider_sql:
                    values.append(DEEPCODEX_MODEL_PROVIDER)
                if model_sql:
                    values.append(DEEPCODEX_DEFAULT_MODEL)
                values.append(row["id"])
                conn.execute(f"UPDATE threads SET rollout_path=?, source=?{provider_sql}{model_sql} WHERE id=?", values)
            count += 1
    return count


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
    legacy_cli_rows: dict[str, dict] | None = None,
) -> tuple[int, int, int, str | None]:
    source_db = source_home / STATE_DB
    target_db = target_home / STATE_DB
    if not source_db.is_file():
        return (0, 0, 0, None)
    legacy_cli_rows = legacy_cli_rows or load_legacy_cli_thread_rows(source_home)
    legacy_cli_ids = set(legacy_cli_rows)

    if not target_db.exists():
        with connect_ro(source_db) as src:
            source_count = src.execute("SELECT count(*) AS n FROM threads").fetchone()["n"] if table_exists(src, "threads") else 0
        if dry_run:
            return (int(source_count), 0, 0, "seed")
        sqlite_backup(source_db, target_db)
        with connect_rw(target_db) as dst:
            with dst:
                imported = sanitize_seeded_state(dst, source_home, target_home, legacy_cli_rows)
        return (imported, 0, 0, "seed")

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
        target_source = {
            str(row["id"]): str(row["source"])
            for row in dst.execute("SELECT id, source FROM threads").fetchall()
        }
        target_provider = {
            str(row["id"]): str(row["model_provider"])
            for row in dst.execute("SELECT id, model_provider FROM threads").fetchall()
        } if "model_provider" in dst_cols else {}

        thread_rows: list[dict] = []
        skipped = 0
        for row in source_rows:
            thread_id = str(row["id"])
            source_updated = int(row["updated_at"] or 0)
            legacy_needs_refresh = thread_id in legacy_cli_ids and target_source.get(thread_id) != "vscode"
            provider_needs_refresh = "model_provider" in common and target_provider.get(thread_id) != DEEPCODEX_MODEL_PROVIDER
            if (
                not legacy_needs_refresh
                and not provider_needs_refresh
                and thread_id in target_updated
                and target_updated[thread_id] >= source_updated
            ):
                skipped += 1
                continue
            data = {name: row[name] for name in common}
            if thread_id in legacy_cli_ids:
                data = normalize_legacy_cli_thread_data(data, legacy_cli_rows[thread_id], source_home, target_home)
            else:
                data = normalize_imported_thread_data(data, source_home, target_home)
            thread_rows.append(data)

        if not thread_rows:
            return (0, skipped, 0, None)
        if dry_run:
            return (len(thread_rows), skipped, 0, None)

        backup = backup_target_state(target_db)
        if verbose:
            log(f"  backed up state -> {backup}")

        changed_ids = [str(row["id"]) for row in thread_rows]
        with dst:
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
                    insert_or_replace_row(dst, "thread_spawn_edges", {name: row[name] for name in edge_common})

        return (len(thread_rows), skipped, 0, None)


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

    legacy_cli_rows = load_legacy_cli_thread_rows(source_home)
    summary = mirror_conversation_files(
        source_home,
        target_home,
        dry_run=args.dry_run,
        verbose=args.verbose,
        legacy_cli_ids=set(legacy_cli_rows),
    )
    legacy_converted = convert_legacy_cli_rollouts(
        source_home,
        target_home,
        legacy_cli_rows,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    index_changed, index_pruned = merge_session_index(
        source_home,
        target_home,
        dry_run=args.dry_run,
        extra_records=legacy_cli_session_index_records(legacy_cli_rows),
    )
    state_imported, state_skipped, state_pruned, state_mode = sync_state_db(
        source_home,
        target_home,
        dry_run=args.dry_run,
        verbose=args.verbose,
        legacy_cli_rows=legacy_cli_rows,
    )
    sidebar = sync_sidebar_state(source_home, target_home, dry_run=args.dry_run)
    history_added = 0
    if args.include_history:
        history_added = merge_history(source_home, target_home, dry_run=args.dry_run, verbose=args.verbose)

    summary.update(
        {
            "session_index_changed": index_changed,
            "session_index_pruned": index_pruned,
            "legacy_cli_rollouts_converted": legacy_converted,
            "state_threads_imported": state_imported,
            "state_threads_skipped": state_skipped,
            "state_threads_pruned": state_pruned,
            "state_mode": state_mode,
            "legacy_cli_threads": len(legacy_cli_rows),
            "sidebar_state_keys_changed": sidebar["keys_changed"],
            "sidebar_codex_projectless_threads": sidebar["codex_projectless_threads"],
            "sidebar_total_projectless_threads": sidebar["total_projectless_threads"],
            "sidebar_codex_projects": sidebar["codex_projects"],
            "sidebar_total_projects": sidebar["total_projects"],
            "history_added": history_added,
        }
    )
    write_summary_manifest(target_home, summary, dry_run=args.dry_run)

    verb = "would import" if args.dry_run else "imported"
    log(f"Sessions: {verb} {summary['sessions_copied']}, skipped {summary['sessions_skipped']}.")
    log(f"Archived: {verb} {summary['archived_sessions_copied']}, skipped {summary['archived_sessions_skipped']}.")
    log(f"Shell snapshots: {verb} {summary['shell_snapshots_copied']}, skipped {summary['shell_snapshots_skipped']}.")
    log(f"Legacy CLI: {'would convert' if args.dry_run else 'converted'} {legacy_converted} desktop-compatible rollouts.")
    log(f"Session index: {'would update' if args.dry_run else 'updated'} {index_changed} records.")
    log(f"State index: {verb} {state_imported} threads, skipped {state_skipped}.")
    log(
        "Sidebar state: "
        f"{'would merge' if args.dry_run else 'merged'} "
        f"{sidebar['codex_projectless_threads']} Codex projectless chats and "
        f"{sidebar['codex_projects']} Codex projects; DeepCodeX now keeps "
        f"{sidebar['total_projectless_threads']} projectless chats and "
        f"{sidebar['total_projects']} projects."
    )
    if legacy_cli_rows:
        log(f"Legacy CLI sessions: exposed {len(legacy_cli_rows)} records through the DeepCodeX UI index.")
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
        local_sid = "019e8ccc-cccc-7ccc-8ccc-cccccccccccc"
        source_rollout = source / "sessions/2026/06/01" / f"rollout-2026-06-01T00-00-00-{sid}.jsonl"
        legacy_rollout = source / "sessions/2026/06/01" / f"rollout-2026-06-01T00-00-00-{legacy_sid}.jsonl"
        source_rollout.parent.mkdir(parents=True)
        source_rollout.write_text(
            '{"type":"session_meta","payload":{"id":"' + sid + '","model_provider":"openai"}}\n'
            + '{"type":"turn_context","payload":{"model":"gpt-5.5"}}\n'
            + json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hello"}],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_rollout.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {
                        "id": legacy_sid,
                        "cwd": "/tmp/project",
                        "originator": "codex-tui",
                        "source": "cli",
                        "model_provider": "openai",
                    },
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "turn_context",
                    "payload": {
                        "turn_id": "legacy-turn",
                        "cwd": "/tmp/project",
                        "approval_policy": "on-request",
                        "sandbox_policy": {"type": "workspace-write"},
                        "permission_profile": {"type": "managed"},
                        "model": "gpt-5.5",
                    },
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "legacy hello"}],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
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
        write_global_state(
            source,
            {
                "project-order": ["/tmp/project"],
                "projectless-thread-ids": [legacy_sid, sid],
                "thread-workspace-root-hints": {legacy_sid: "/tmp/project", sid: "/tmp/project"},
                "thread-projectless-output-directories": {legacy_sid: "/tmp/out"},
                "pinned-thread-ids": [sid],
                "electron-saved-workspace-roots": [],
                "active-workspace-roots": ["/tmp/project"],
            },
        )
        write_global_state(
            target,
            {
                "project-order": ["/tmp/deepcodex-project"],
                "projectless-thread-ids": [local_sid],
                "thread-workspace-root-hints": {local_sid: "/tmp/deepcodex-project"},
                "pinned-thread-ids": [local_sid],
            },
        )
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
                    '{"type":"workspace-write"}',
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
        copied_records = read_jsonl(copied)
        copied_meta = copied_records[0].get("payload", {})
        copied_turn = copied_records[1].get("payload", {})
        if copied_meta.get("model_provider") != DEEPCODEX_MODEL_PROVIDER:
            raise AssertionError("imported rollout session metadata provider was not normalized")
        if copied_turn.get("model") != DEEPCODEX_DEFAULT_MODEL:
            raise AssertionError("imported rollout turn model was not normalized")
        if not (target / "archived_sessions" / f"rollout-2026-05-01T00-00-00-{sid}.jsonl").is_file():
            raise AssertionError("archived rollout was not copied")
        with sqlite3.connect(target / STATE_DB) as conn:
            row = conn.execute("SELECT rollout_path, model_provider FROM threads WHERE id=?", (sid,)).fetchone()
        if row is None or row[0] != str(copied):
            raise AssertionError("thread state was not imported with rewritten rollout path")
        if row[1] != DEEPCODEX_MODEL_PROVIDER:
            raise AssertionError("imported Codex thread provider was not normalized for DeepCodeX")
        with sqlite3.connect(target / STATE_DB) as conn:
            legacy_target = target / "sessions/2026/06/01" / legacy_rollout.name
            legacy_row = conn.execute("SELECT rollout_path, source, model_provider FROM threads WHERE id=?", (legacy_sid,)).fetchone()
            legacy_tool = conn.execute("SELECT thread_id FROM thread_dynamic_tools WHERE thread_id=?", (legacy_sid,)).fetchone()
        if legacy_row is None or legacy_row[0] != str(legacy_target) or legacy_row[1] != "vscode":
            raise AssertionError("legacy CLI thread state was not imported as a desktop-compatible thread")
        if legacy_row[2] != DEEPCODEX_MODEL_PROVIDER:
            raise AssertionError("legacy CLI thread provider was not normalized for DeepCodeX")
        if legacy_tool is None:
            raise AssertionError("legacy CLI dynamic tools were not imported")
        if not (target / "session_index.jsonl").is_file():
            raise AssertionError("session index was not written")
        if legacy_sid not in (target / "session_index.jsonl").read_text(encoding="utf-8"):
            raise AssertionError("legacy CLI thread was not written to the session index")
        legacy_records = read_jsonl(legacy_target)
        if legacy_records[0]["payload"].get("source") != "vscode":
            raise AssertionError("legacy CLI session_meta was not normalized")
        if legacy_records[1]["payload"].get("permission_profile") != {"type": "disabled"}:
            raise AssertionError("legacy CLI turn_context was not normalized")
        if not (target / "history.jsonl").is_file():
            raise AssertionError("history was not merged")
        sidebar = load_global_state(target)
        if sidebar.get("projectless-thread-ids") != [legacy_sid, sid, local_sid]:
            raise AssertionError(f"sidebar projectless threads were not merged correctly: {sidebar.get('projectless-thread-ids')}")
        if sidebar.get("project-order") != ["/tmp/project", "/tmp/deepcodex-project"]:
            raise AssertionError(f"sidebar projects were not merged correctly: {sidebar.get('project-order')}")
        hints = sidebar.get("thread-workspace-root-hints")
        if not isinstance(hints, dict) or hints.get(local_sid) != "/tmp/deepcodex-project" or hints.get(sid) != "~":
            raise AssertionError("sidebar workspace hints did not preserve both Codex and DeepCodeX conversations")
    log("session import selftest OK")
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest()
    return run_import(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
