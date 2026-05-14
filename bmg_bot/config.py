from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_int_list(raw: str | None) -> list[int]:
    if not raw or not raw.strip():
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    owner_id: int
    admin_ids: frozenset[int]
    archive_channel_ids: tuple[int, ...]
    max_users: int
    sqlite_path: str
    antiflood_seconds: float
    relay_concurrency: int
    backup_interval_seconds: int
    backup_dir: str
    backup_keep: int
    health_check: bool
    # High-traffic / outbox
    outbox_workers: int
    outbound_global_send_limit: int
    aiohttp_connector_limit: int
    start_bucket_capacity: float
    start_bucket_refill_per_sec: float
    start_concurrency: int
    start_per_user_debounce_sec: float
    global_msg_bucket_capacity: float
    global_msg_refill_per_sec: float
    sliding_window_sec: float
    sliding_window_max_msgs: int
    rate_limiter_max_tracked_users: int
    cleanup_interval_sec: int
    outbox_done_retention_sec: int
    update_tasks_concurrency: int

    def is_admin(self, user_id: int) -> bool:
        return user_id == self.owner_id or user_id in self.admin_ids

    def admin_dm_ids(self) -> tuple[int, ...]:
        ids: list[int] = [self.owner_id]
        for aid in sorted(self.admin_ids):
            if aid not in ids:
                ids.append(aid)
        return tuple(ids)


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    owner_raw = os.getenv("OWNER_ID", "").strip()
    if not owner_raw:
        raise RuntimeError("OWNER_ID is required (Telegram user id of the primary owner)")
    owner_id = int(owner_raw)

    extra_admins = _parse_int_list(os.getenv("ADMIN_IDS"))
    admin_ids = frozenset(a for a in extra_admins if a != owner_id)

    channels_raw = os.getenv("ARCHIVE_CHANNEL_IDS", "").strip()
    if channels_raw:
        archive = tuple(_parse_int_list(channels_raw))
    else:
        archive = (
            -1003759990321,
            -1003947622092,
            -1003839014211,
            -1003877842234,
        )

    data_dir = os.getenv("DATA_DIR", "data").strip() or "data"
    os.makedirs(data_dir, exist_ok=True)

    sqlite_default = os.path.join(data_dir, "bot2.db")
    sqlite_path = os.getenv("SQLITE_PATH", sqlite_default).strip() or sqlite_default
    parent = os.path.dirname(os.path.abspath(sqlite_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    max_users = int(os.getenv("MAX_USERS", "1000"))
    antiflood = float(os.getenv("ANTIFLOOD_SECONDS", "0.35"))
    relay_concurrency = int(os.getenv("RELAY_CONCURRENCY", "20"))

    backup_interval = int(os.getenv("BACKUP_INTERVAL_SECONDS", str(6 * 3600)))
    backup_dir = os.getenv("BACKUP_DIR", "backups").strip() or "backups"
    backup_keep = int(os.getenv("BACKUP_KEEP", "5"))

    health = os.getenv("HEALTH_CHECK", "").lower() in {"1", "true", "yes"}
    if os.getenv("PORT"):
        health = True

    outbox_workers = int(os.getenv("OUTBOX_WORKERS", "8"))
    _ogl = os.getenv("OUTBOUND_GLOBAL_SEND_LIMIT", "").strip()
    outbound_global_send_limit = int(_ogl) if _ogl else relay_concurrency
    aiohttp_connector_limit = int(os.getenv("AIOHTTP_CONNECTOR_LIMIT", "256"))

    start_bucket_capacity = float(os.getenv("START_BUCKET_CAPACITY", "200"))
    start_bucket_refill = float(os.getenv("START_BUCKET_REFILL_PER_SEC", "45"))
    start_concurrency = int(os.getenv("START_CONCURRENCY", "80"))
    start_debounce = float(os.getenv("START_PER_USER_DEBOUNCE_SEC", "5"))

    g_cap = float(os.getenv("GLOBAL_MSG_BUCKET_CAPACITY", "120"))
    g_refill = float(os.getenv("GLOBAL_MSG_BUCKET_REFILL_PER_SEC", "40"))
    slide_sec = float(os.getenv("SLIDING_WINDOW_SEC", "12"))
    slide_max = int(os.getenv("SLIDING_WINDOW_MAX_MSGS", "48"))
    max_tracked = int(os.getenv("RATE_LIMITER_MAX_TRACKED_USERS", "50000"))

    cleanup_interval = int(os.getenv("CLEANUP_INTERVAL_SEC", "600"))
    outbox_retention = int(os.getenv("OUTBOX_DONE_RETENTION_SEC", str(7 * 86400)))

    update_tasks = int(os.getenv("UPDATE_TASKS_CONCURRENCY", "400"))

    return Settings(
        bot_token=token,
        owner_id=owner_id,
        admin_ids=admin_ids,
        archive_channel_ids=archive,
        max_users=max_users,
        sqlite_path=sqlite_path,
        antiflood_seconds=max(0.0, antiflood),
        relay_concurrency=max(1, min(relay_concurrency, 50)),
        backup_interval_seconds=max(0, backup_interval),
        backup_dir=backup_dir,
        backup_keep=max(1, min(backup_keep, 50)),
        health_check=health,
        outbox_workers=max(1, min(outbox_workers, 32)),
        outbound_global_send_limit=max(5, min(outbound_global_send_limit, 200)),
        aiohttp_connector_limit=max(50, min(aiohttp_connector_limit, 2000)),
        start_bucket_capacity=max(10.0, start_bucket_capacity),
        start_bucket_refill_per_sec=max(1.0, start_bucket_refill),
        start_concurrency=max(5, min(start_concurrency, 500)),
        start_per_user_debounce_sec=max(1.0, start_debounce),
        global_msg_bucket_capacity=max(10.0, g_cap),
        global_msg_refill_per_sec=max(1.0, g_refill),
        sliding_window_sec=max(3.0, slide_sec),
        sliding_window_max_msgs=max(5, slide_max),
        rate_limiter_max_tracked_users=max(1000, min(max_tracked, 500_000)),
        cleanup_interval_sec=max(60, cleanup_interval),
        outbox_done_retention_sec=max(3600, outbox_retention),
        update_tasks_concurrency=max(32, min(update_tasks, 2000)),
    )
