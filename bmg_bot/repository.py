from __future__ import annotations

import time
from dataclasses import dataclass

from bmg_bot.database import Database, dumps_activity, loads_activity, trim_activity, week_activity_count


@dataclass(slots=True)
class PendingInfo:
    alias: str
    media: int


@dataclass(slots=True)
class UserStats:
    messages: int
    photos: int
    videos: int
    documents: int
    warns: int
    activity: list[float]


class LobbyRepository:
    """Write-through cache over SQLite for hot paths (relay, admin panel)."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.users: dict[int, str] = {}
        self.pending_users: dict[int, PendingInfo] = {}
        self.banned_users: dict[int, str] = {}
        self.user_stats: dict[int, UserStats] = {}
        self.waiting_name: set[int] = set()

    async def load_from_db(self) -> None:
        self.users.clear()
        self.pending_users.clear()
        self.banned_users.clear()
        self.user_stats.clear()
        self.waiting_name.clear()

        for row in await self.db.fetchall("SELECT user_id, alias FROM users"):
            self.users[int(row["user_id"])] = str(row["alias"])

        for row in await self.db.fetchall("SELECT user_id, alias, media_count FROM pending"):
            self.pending_users[int(row["user_id"])] = PendingInfo(
                alias=str(row["alias"]),
                media=int(row["media_count"]),
            )

        for row in await self.db.fetchall("SELECT user_id, reason FROM banned"):
            self.banned_users[int(row["user_id"])] = str(row["reason"])

        for row in await self.db.fetchall(
            "SELECT user_id, messages, photos, videos, documents, warns, activity_ts FROM user_stats"
        ):
            self.user_stats[int(row["user_id"])] = UserStats(
                messages=int(row["messages"]),
                photos=int(row["photos"]),
                videos=int(row["videos"]),
                documents=int(row["documents"]),
                warns=int(row["warns"]),
                activity=loads_activity(row["activity_ts"] if row["activity_ts"] is not None else "[]"),
            )

        for row in await self.db.fetchall("SELECT user_id FROM waiting_alias"):
            self.waiting_name.add(int(row["user_id"]))

    async def add_waiting_alias(self, user_id: int) -> None:
        self.waiting_name.add(user_id)
        await self.db.execute("INSERT OR IGNORE INTO waiting_alias(user_id) VALUES(?)", (user_id,))

    async def remove_waiting_alias(self, user_id: int) -> None:
        self.waiting_name.discard(user_id)
        await self.db.execute("DELETE FROM waiting_alias WHERE user_id = ?", (user_id,))

    async def set_pending(self, user_id: int, alias: str) -> None:
        self.pending_users[user_id] = PendingInfo(alias=alias, media=0)
        await self.db.execute(
            "INSERT INTO pending(user_id, alias, media_count) VALUES(?,?,0) "
            "ON CONFLICT(user_id) DO UPDATE SET alias = excluded.alias, media_count = 0",
            (user_id, alias),
        )

    async def bump_pending_media(self, user_id: int) -> int:
        info = self.pending_users.get(user_id)
        if not info:
            return 0
        info.media += 1
        await self.db.execute(
            "UPDATE pending SET media_count = ? WHERE user_id = ?",
            (info.media, user_id),
        )
        return info.media

    async def delete_pending(self, user_id: int) -> PendingInfo | None:
        info = self.pending_users.pop(user_id, None)
        await self.db.execute("DELETE FROM pending WHERE user_id = ?", (user_id,))
        return info

    async def approve_user(self, user_id: int, alias: str) -> None:
        now = time.time()
        self.users[user_id] = alias
        self.user_stats[user_id] = UserStats(0, 0, 0, 0, 0, [])
        await self.db.execute("DELETE FROM pending WHERE user_id = ?", (user_id,))
        self.pending_users.pop(user_id, None)
        await self.db.execute(
            "INSERT INTO users(user_id, alias, joined_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET alias = excluded.alias",
            (user_id, alias, now),
        )
        await self.db.execute(
            "INSERT INTO user_stats(user_id, messages, photos, videos, documents, warns, activity_ts) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET messages=0, photos=0, videos=0, documents=0, warns=0, activity_ts='[]'",
            (user_id, 0, 0, 0, 0, 0, "[]"),
        )

    async def remove_user(self, user_id: int) -> None:
        self.users.pop(user_id, None)
        self.user_stats.pop(user_id, None)
        await self.db.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
        await self.db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    async def ban_user(self, user_id: int, reason: str) -> None:
        self.banned_users[user_id] = reason
        await self.remove_user(user_id)
        await self.delete_pending(user_id)
        await self.remove_waiting_alias(user_id)
        await self.db.execute(
            "INSERT INTO banned(user_id, reason) VALUES(?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET reason = excluded.reason",
            (user_id, reason),
        )

    async def increment_stat(
        self,
        user_id: int,
        *,
        messages: int = 0,
        photos: int = 0,
        videos: int = 0,
        documents: int = 0,
        record_activity: bool = False,
    ) -> None:
        st = self.user_stats.get(user_id)
        if not st:
            return
        st.messages += messages
        st.photos += photos
        st.videos += videos
        st.documents += documents
        if record_activity:
            st.activity.append(time.time())
            st.activity = trim_activity(st.activity)
        await self.db.execute(
            "UPDATE user_stats SET messages=?, photos=?, videos=?, documents=?, activity_ts=? "
            "WHERE user_id = ?",
            (st.messages, st.photos, st.videos, st.documents, dumps_activity(st.activity), user_id),
        )

    def activity_window_count(self, user_id: int) -> int:
        st = self.user_stats.get(user_id)
        if not st:
            return 0
        return week_activity_count(st.activity)

    async def fetch_joined_at(self, user_id: int) -> float | None:
        row = await self.db.fetchone("SELECT joined_at FROM users WHERE user_id = ?", (user_id,))
        if row is None:
            return None
        return float(row["joined_at"])

    async def list_member_ids(self) -> list[int]:
        return list(self.users.keys())
