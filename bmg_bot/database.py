from __future__ import annotations

import asyncio
import json
import time

import aiosqlite


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=8000;
PRAGMA temp_store=MEMORY;
PRAGMA cache_size=-64000;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    alias TEXT NOT NULL,
    joined_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pending (
    user_id INTEGER PRIMARY KEY,
    alias TEXT NOT NULL,
    media_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS banned (
    user_id INTEGER PRIMARY KEY,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_stats (
    user_id INTEGER PRIMARY KEY,
    messages INTEGER NOT NULL DEFAULT 0,
    photos INTEGER NOT NULL DEFAULT 0,
    videos INTEGER NOT NULL DEFAULT 0,
    documents INTEGER NOT NULL DEFAULT 0,
    warns INTEGER NOT NULL DEFAULT 0,
    activity_ts TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS waiting_alias (
    user_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    priority INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 14,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_error TEXT,
    source TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_outbox_status_prio ON outbox(status, priority DESC, id ASC);

CREATE TABLE IF NOT EXISTS join_throttle (
    user_id INTEGER PRIMARY KEY,
    last_seen REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        await self.reset_stale_outbox()

    async def reset_stale_outbox(self) -> None:
        now = time.time()
        async with self._lock:
            await self.connection.execute(
                "UPDATE outbox SET status = 'pending', updated_at = ?, last_error = coalesce(last_error,'') || ';recovered'"
                " WHERE status = 'working'",
                (now,),
            )
            await self.connection.commit()

    async def outbox_enqueue(
        self,
        *,
        priority: int,
        kind: str,
        payload: str,
        source: str,
        max_attempts: int = 14,
    ) -> int:
        now = time.time()
        async with self._lock:
            cur = await self.connection.execute(
                "INSERT INTO outbox(priority, kind, payload, status, attempts, max_attempts, created_at, updated_at, source) "
                "VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?)",
                (priority, kind, payload, max_attempts, now, now, source),
            )
            await self.connection.commit()
            return int(cur.lastrowid)

    async def outbox_enqueue_many(
        self,
        rows: list[tuple[int, str, str, str, int]],
    ) -> list[int]:
        """rows: (priority, kind, payload_json, source, max_attempts)"""
        now = time.time()
        ids: list[int] = []
        async with self._lock:
            for priority, kind, payload, source, max_attempts in rows:
                cur = await self.connection.execute(
                    "INSERT INTO outbox(priority, kind, payload, status, attempts, max_attempts, created_at, updated_at, source) "
                    "VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?)",
                    (priority, kind, payload, max_attempts, now, now, source),
                )
                ids.append(int(cur.lastrowid))
            await self.connection.commit()
        return ids

    async def outbox_claim_one(self) -> dict[str, object] | None:
        now = time.time()
        async with self._lock:
            cur = await self.connection.execute(
                "SELECT id, kind, payload, attempts, max_attempts FROM outbox WHERE status = 'pending' "
                "ORDER BY priority DESC, id ASC LIMIT 1",
            )
            row = await cur.fetchone()
            if row is None:
                return None
            jid = int(row["id"])
            await self.connection.execute(
                "UPDATE outbox SET status = 'working', updated_at = ? WHERE id = ? AND status = 'pending'",
                (now, jid),
            )
            await self.connection.commit()
            return {
                "id": jid,
                "kind": str(row["kind"]),
                "payload": str(row["payload"]),
                "attempts": int(row["attempts"]),
                "max_attempts": int(row["max_attempts"]),
            }

    async def outbox_mark_done(self, job_id: int) -> None:
        now = time.time()
        await self.execute(
            "UPDATE outbox SET status = 'done', updated_at = ?, last_error = NULL WHERE id = ? AND status = 'working'",
            (now, job_id),
        )

    async def outbox_fail(self, job_id: int, err: str) -> str:
        """Return next status: pending|dead"""
        now = time.time()
        async with self._lock:
            cur = await self.connection.execute(
                "SELECT attempts, max_attempts FROM outbox WHERE id = ? AND status = 'working'",
                (job_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return "missing"
            attempts = int(row["attempts"]) + 1
            max_attempts = int(row["max_attempts"])
            if attempts >= max_attempts:
                await self.connection.execute(
                    "UPDATE outbox SET status = 'dead', attempts = ?, updated_at = ?, last_error = ? WHERE id = ? AND status = 'working'",
                    (attempts, now, err[:2000], job_id),
                )
                await self.connection.commit()
                return "dead"
            await self.connection.execute(
                "UPDATE outbox SET status = 'pending', attempts = ?, updated_at = ?, last_error = ? WHERE id = ? AND status = 'working'",
                (attempts, now, err[:2000], job_id),
            )
            await self.connection.commit()
            return "pending"

    async def outbox_pending_count(self) -> int:
        row = await self.fetchone(
            "SELECT COUNT(*) AS c FROM outbox WHERE status IN ('pending','working')",
        )
        return int(row["c"]) if row else 0

    async def outbox_cleanup_done(self, *, older_than_sec: float) -> int:
        cutoff = time.time() - older_than_sec
        cur = await self.execute("DELETE FROM outbox WHERE status = 'done' AND updated_at < ?", (cutoff,))
        return cur.rowcount if cur.rowcount is not None else 0

    async def join_start_allow(self, user_id: int, debounce_sec: float) -> bool:
        """Returns False if /start should be ignored as a duplicate burst."""
        now = time.time()
        async with self._lock:
            cur = await self.connection.execute(
                "SELECT last_seen FROM join_throttle WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
            prev_ts = float(row["last_seen"]) if row else 0.0
            if row is not None and now - prev_ts < debounce_sec:
                return False
            await self.connection.execute(
                "INSERT INTO join_throttle(user_id, last_seen) VALUES(?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET last_seen = excluded.last_seen",
                (user_id, now),
            )
            await self.connection.commit()
            return True

    async def join_throttle_prune(self, *, older_than_sec: float) -> int:
        cutoff = time.time() - older_than_sec
        cur = await self.execute("DELETE FROM join_throttle WHERE last_seen < ?", (cutoff,))
        return cur.rowcount if cur.rowcount is not None else 0

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def execute(self, sql: str, params: tuple | list = ()) -> aiosqlite.Cursor:
        async with self._lock:
            cur = await self.connection.execute(sql, params)
            await self.connection.commit()
            return cur

    async def executemany(self, sql: str, seq: list[tuple]) -> None:
        async with self._lock:
            await self.connection.executemany(sql, seq)
            await self.connection.commit()

    async def fetchone(self, sql: str, params: tuple | list = ()) -> aiosqlite.Row | None:
        async with self._lock:
            cur = await self.connection.execute(sql, params)
            row = await cur.fetchone()
            return row

    async def fetchall(self, sql: str, params: tuple | list = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            cur = await self.connection.execute(sql, params)
            rows = await cur.fetchall()
            return list(rows)

    async def get_kv(self, key: str, default: str | None = None) -> str | None:
        row = await self.fetchone("SELECT value FROM kv WHERE key = ?", (key,))
        if row is None:
            return default
        return str(row["value"])

    async def set_kv(self, key: str, value: str) -> None:
        await self.execute(
            "INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def week_activity_count(timestamps: list[float], *, now: float | None = None) -> int:
    now = now or time.time()
    cutoff = now - 7 * 86400
    return sum(1 for t in timestamps if t >= cutoff)


def trim_activity(timestamps: list[float], *, now: float | None = None) -> list[float]:
    now = now or time.time()
    cutoff = now - 7 * 86400
    return [t for t in timestamps if t >= cutoff]


def loads_activity(raw: str | None) -> list[float]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [float(x) for x in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def dumps_activity(timestamps: list[float]) -> str:
    return json.dumps(timestamps)
