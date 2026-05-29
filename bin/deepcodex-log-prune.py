#!/usr/bin/env python3
"""
DeepCodex 日志库保留作业 (logs_2.sqlite retention)

为什么存在：logs_2.sqlite 是 Codex app-server 自己的日志库，没有任何保留机制，
实测 3 天涨到 240MB（75% 是 TRACE/DEBUG 行）。不清理迟早涨到 GB 级。

为什么安全（稳定第一）：
- 该库是 WAL 模式 + auto_vacuum=INCREMENTAL。
- WAL 下 DELETE 不阻塞 app 的并发读写。
- 用 `PRAGMA incremental_vacuum` 把删后空出的页还给系统，不需要会抢独占锁的 full VACUUM，
  所以可以带 app 一起跑，不会把 DeepCodex 卡死。
- 只删"老日志行"，不动表结构；watcher 们按 max(id) 跟踪，删旧行不影响它们。

用法：
    deepcodex-log-prune.py              # 删 3 天前的日志行并回收空间（默认保留 3 天）
    deepcodex-log-prune.py --days 7     # 自定义保留天数
    deepcodex-log-prune.py --dry-run    # 只报告会删多少，不动数据
"""
import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

LOG_DB = Path(os.environ.get(
    "DEEPCODEX_LOG_DB",
    str(Path(os.environ.get("DEEPCODEX_HOME", "~/.codex-deepseek")).expanduser() / "logs_2.sqlite"),
))
DEFAULT_RETENTION_DAYS = int(os.environ.get("DEEPCODEX_LOG_RETENTION_DAYS", "3"))


def file_size_mb(path: Path) -> float:
    try:
        return path.stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune old rows from DeepCodex logs_2.sqlite.")
    parser.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS,
                        help=f"retention window in days (default {DEFAULT_RETENTION_DAYS})")
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    parser.add_argument("--vacuum", action="store_true",
                        help="删后跑 full VACUUM 把空间真正还给磁盘（要独占锁，只在 DeepCodex 关闭时用）")
    args = parser.parse_args()

    if not LOG_DB.exists():
        print(f"[log-prune] DB not found: {LOG_DB}")
        return 0

    cutoff = int(time.time()) - args.days * 86400
    size_before = file_size_mb(LOG_DB)

    conn = sqlite3.connect(str(LOG_DB), timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout = 10000;")
        total = conn.execute("select count(*) from logs").fetchone()[0]
        old = conn.execute("select count(*) from logs where ts < ?", (cutoff,)).fetchone()[0]

        if args.dry_run:
            print(f"[log-prune] DRY-RUN: would delete {old}/{total} rows older than {args.days}d "
                  f"(cutoff ts={cutoff}); db={size_before:.1f}MB")
            return 0

        if old == 0 and not args.vacuum:
            print(f"[log-prune] nothing to delete (total={total}, db={size_before:.1f}MB)")
            return 0

        if old > 0:
            conn.execute("delete from logs where ts < ?", (cutoff,))
            conn.commit()
            # 把删后空闲页还给系统（auto_vacuum=INCREMENTAL，无需 full VACUUM 独占锁）。
            # 注意：app 在线时腾出的页常被立刻复用，文件多半不缩、只是封顶不再涨。
            conn.execute("PRAGMA incremental_vacuum;")
            conn.commit()
            # 收缩 WAL 文件
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        remaining = conn.execute("select count(*) from logs").fetchone()[0]

        vacuumed = False
        if args.vacuum:
            # full VACUUM 重写整库、真正还盘，但要独占锁——DeepCodex 开着会拿不到锁报错。
            try:
                conn.execute("VACUUM;")
                vacuumed = True
            except sqlite3.OperationalError as exc:
                print(f"[log-prune] VACUUM 跳过（库被占用，请关闭 DeepCodex 再试）: {exc}")
    finally:
        conn.close()

    size_after = file_size_mb(LOG_DB)
    tail = " +VACUUM" if args.vacuum and vacuumed else ""
    print(f"[log-prune] deleted {old} rows (kept {remaining}); "
          f"db {size_before:.1f}MB -> {size_after:.1f}MB; retention={args.days}d{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
