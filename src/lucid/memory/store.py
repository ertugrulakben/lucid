"""SQLite-backed memory store.

Three tables persist what Lucid has learned across sessions:

- ``facts``: free-form key/value pairs Claude extracts from successful runs
  ("In Gmail, Ctrl+Shift+A opens the attach dialog.").
- ``files``: a lightweight index of files the user has recently touched, so
  Answer-mode queries like "where did I save last month's invoice" can
  resolve locally.
- ``task_patterns``: short summaries of successful Execute tasks, retrieved
  by keyword to seed future Execute prompts ("you solved this kind of task
  before like this").

All data lives inside ``data/memory.db`` under the Lucid project; nothing is
written to APPDATA. The store is deliberately tiny — no vector DB, no
dependencies beyond sqlite3. BM25-ish ranking is done in Python on demand.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("lucid.memory")


SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    created_at REAL NOT NULL,
    last_used_at REAL NOT NULL,
    uses INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_facts_topic ON facts(topic);
CREATE INDEX IF NOT EXISTS idx_facts_lastused ON facts(last_used_at DESC);

CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    kind TEXT,
    last_accessed_at REAL NOT NULL,
    tags TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_recent ON files(last_accessed_at DESC);

CREATE TABLE IF NOT EXISTS task_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal TEXT NOT NULL,
    summary TEXT NOT NULL,
    target_app TEXT,
    succeeded INTEGER NOT NULL DEFAULT 1,
    step_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patterns_app ON task_patterns(target_app);
CREATE INDEX IF NOT EXISTS idx_patterns_time ON task_patterns(created_at DESC);

CREATE TABLE IF NOT EXISTS captcha_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    succeeded INTEGER NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_captcha_at ON captcha_attempts(at DESC);
"""


@dataclass
class Fact:
    topic: str
    content: str
    source: str | None = None
    id: int | None = None
    created_at: float = 0.0
    last_used_at: float = 0.0
    uses: int = 0


@dataclass
class FileRecord:
    path: str
    kind: str | None = None
    last_accessed_at: float = 0.0
    tags: str | None = None


@dataclass
class TaskPattern:
    goal: str
    summary: str
    target_app: str | None = None
    succeeded: bool = True
    step_count: int = 0
    id: int | None = None
    created_at: float = 0.0


_STOP_WORDS = {
    "bir",
    "ve",
    "için",
    "ile",
    "de",
    "da",
    "bu",
    "şu",
    "the",
    "a",
    "an",
    "to",
    "of",
    "in",
    "on",
    "at",
    "is",
    "are",
    "be",
    "lucid",
    "open",
    "aç",
    "yap",
}


def _tokens(text: str) -> list[str]:
    return [
        t
        for t in re.split(r"\W+", (text or "").lower())
        if t and t not in _STOP_WORDS and len(t) > 1
    ]


class MemoryStore:
    """Thread-safe SQLite wrapper with tiny ranking helpers.

    One connection per thread via thread-local storage — sqlite3 connections
    are not safe to share.
    """

    def __init__(
        self,
        db_path: Path,
        max_facts: int = 2000,
        max_files: int = 500,
        max_task_patterns: int = 500,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.max_facts = max_facts
        self.max_files = max_files
        self.max_task_patterns = max_task_patterns
        with self._conn() as c:
            c.executescript(SCHEMA)
            c.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=5.0, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    # ---------- facts ----------

    def add_fact(self, topic: str, content: str, source: str | None = None) -> int:
        topic = topic.strip()
        content = content.strip()
        if not topic or not content:
            return 0
        now = time.time()
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO facts(topic, content, source, created_at, last_used_at, uses) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (topic, content, source, now, now),
            )
            c.commit()
            self._trim("facts", self.max_facts)
            return int(cur.lastrowid or 0)

    def recent_facts(self, limit: int = 20) -> list[Fact]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, topic, content, source, created_at, last_used_at, uses "
                "FROM facts ORDER BY last_used_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def search_facts(self, query: str, limit: int = 5) -> list[Fact]:
        tokens = _tokens(query)
        if not tokens:
            return []
        like_clauses = " OR ".join(["topic LIKE ? OR content LIKE ?" for _ in tokens])
        params: list[Any] = []
        for t in tokens:
            params.extend([f"%{t}%", f"%{t}%"])
        sql = (
            "SELECT id, topic, content, source, created_at, last_used_at, uses, "
            " (CASE WHEN topic LIKE ? THEN 3 ELSE 0 END) AS boost "
            "FROM facts WHERE " + like_clauses + " LIMIT ?"
        )
        params = [f"%{tokens[0]}%"] + params + [limit * 4]
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        scored: list[tuple[float, Fact]] = []
        for r in rows:
            text = f"{r['topic']} {r['content']}".lower()
            score = sum(text.count(t) for t in tokens) + float(r["boost"]) + 0.1 * r["uses"]
            scored.append((score, self._row_to_fact(r)))
        scored.sort(key=lambda p: p[0], reverse=True)
        top = [f for _, f in scored[:limit]]
        if top:
            now = time.time()
            ids = [f.id for f in top if f.id is not None]
            with self._conn() as c:
                c.executemany(
                    "UPDATE facts SET uses = uses + 1, last_used_at = ? WHERE id = ?",
                    [(now, i) for i in ids],
                )
                c.commit()
        return top

    def forget_fact(self, fact_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            c.commit()
            return (cur.rowcount or 0) > 0

    # ---------- files ----------

    def touch_file(self, path: str, kind: str | None = None, tags: str | None = None) -> None:
        now = time.time()
        with self._conn() as c:
            c.execute(
                "INSERT INTO files(path, kind, last_accessed_at, tags) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET last_accessed_at=excluded.last_accessed_at, "
                "kind=COALESCE(excluded.kind, files.kind), tags=COALESCE(excluded.tags, files.tags)",
                (path, kind, now, tags),
            )
            c.commit()
            self._trim("files", self.max_files, order_by="last_accessed_at")

    def recent_files(self, limit: int = 20) -> list[FileRecord]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT path, kind, last_accessed_at, tags FROM files "
                "ORDER BY last_accessed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [FileRecord(**dict(r)) for r in rows]

    def find_files(self, query: str, limit: int = 10) -> list[FileRecord]:
        tokens = _tokens(query)
        if not tokens:
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT path, kind, last_accessed_at, tags FROM files ORDER BY last_accessed_at DESC"
            ).fetchall()
        scored: list[tuple[float, FileRecord]] = []
        for r in rows:
            hay = f"{r['path']} {r['tags'] or ''}".lower()
            score = sum(hay.count(t) for t in tokens)
            if score:
                scored.append((score, FileRecord(**dict(r))))
        scored.sort(key=lambda p: p[0], reverse=True)
        return [f for _, f in scored[:limit]]

    # ---------- task patterns ----------

    def add_task_pattern(
        self,
        goal: str,
        summary: str,
        target_app: str | None = None,
        step_count: int = 0,
        succeeded: bool = True,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO task_patterns(goal, summary, target_app, succeeded, step_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    goal.strip(),
                    summary.strip(),
                    target_app,
                    1 if succeeded else 0,
                    step_count,
                    time.time(),
                ),
            )
            c.commit()
            self._trim("task_patterns", self.max_task_patterns)
            return int(cur.lastrowid or 0)

    def search_task_patterns(
        self, query: str, limit: int = 3, target_app: str | None = None
    ) -> list[TaskPattern]:
        tokens = _tokens(query)
        if not tokens:
            return []
        with self._conn() as c:
            if target_app:
                rows = c.execute(
                    "SELECT id, goal, summary, target_app, succeeded, step_count, created_at "
                    "FROM task_patterns WHERE target_app = ? ORDER BY created_at DESC LIMIT 200",
                    (target_app,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, goal, summary, target_app, succeeded, step_count, created_at "
                    "FROM task_patterns ORDER BY created_at DESC LIMIT 400"
                ).fetchall()
        scored: list[tuple[float, TaskPattern]] = []
        for r in rows:
            hay = f"{r['goal']} {r['summary']}".lower()
            score = sum(hay.count(t) for t in tokens) * (1.0 if r["succeeded"] else 0.3)
            if score:
                scored.append(
                    (
                        score,
                        TaskPattern(
                            id=r["id"],
                            goal=r["goal"],
                            summary=r["summary"],
                            target_app=r["target_app"],
                            succeeded=bool(r["succeeded"]),
                            step_count=r["step_count"],
                            created_at=r["created_at"],
                        ),
                    )
                )
        scored.sort(key=lambda p: p[0], reverse=True)
        return [p for _, p in scored[:limit]]

    # ---------- captcha throttling ----------

    def log_captcha_attempt(self, kind: str, succeeded: bool) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO captcha_attempts(kind, succeeded, at) VALUES (?, ?, ?)",
                (kind, 1 if succeeded else 0, time.time()),
            )
            c.commit()

    def captcha_attempts_last_hour(self) -> int:
        cutoff = time.time() - 3600
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM captcha_attempts WHERE at >= ?",
                (cutoff,),
            ).fetchone()
        return int(row["n"]) if row else 0

    # ---------- utilities ----------

    def stats(self) -> dict[str, int]:
        with self._conn() as c:

            def _count(table: str) -> int:
                row = c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
                return int(row["n"]) if row else 0

            return {
                "facts": _count("facts"),
                "files": _count("files"),
                "task_patterns": _count("task_patterns"),
                "captcha_attempts": _count("captcha_attempts"),
            }

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.conn = None

    # ---------- helpers ----------

    def _trim(self, table: str, limit: int, order_by: str = "id") -> None:
        with self._conn() as c:
            row = c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            n = int(row["n"]) if row else 0
            if n <= limit:
                return
            excess = n - limit
            c.execute(
                f"DELETE FROM {table} WHERE rowid IN "
                f"(SELECT rowid FROM {table} ORDER BY {order_by} ASC LIMIT ?)",
                (excess,),
            )
            c.commit()

    @staticmethod
    def _row_to_fact(r: sqlite3.Row) -> Fact:
        return Fact(
            id=r["id"],
            topic=r["topic"],
            content=r["content"],
            source=r["source"],
            created_at=r["created_at"],
            last_used_at=r["last_used_at"],
            uses=r["uses"],
        )
