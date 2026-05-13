from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from bmg_bot.database import Database
from bmg_bot.metrics import RuntimeMetrics
from bmg_bot.services.archive import ArchiveService
from bmg_bot.telegram_safe import call_with_telegram_retry

log = logging.getLogger(__name__)


class JobPriority:
    """Higher number = claimed first from SQLite outbox."""

    ADMIN = 1_000_000
    RELAY = 100_000
    ARCHIVE = 50_000
    ONBOARDING = 10_000


class OutboundHub:
    """Durable SQLite outbox + worker pool; FloodWait-safe Telegram sends."""

    def __init__(
        self,
        *,
        db: Database,
        bot: Bot,
        metrics: RuntimeMetrics,
        archive: ArchiveService,
        workers: int,
        global_send_bucket: int,
    ) -> None:
        self._db = db
        self._bot = bot
        self._metrics = metrics
        self._archive = archive
        self._workers_n = max(1, min(workers, 32))
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._send_bucket = asyncio.Semaphore(max(1, global_send_bucket))

    def start(self) -> None:
        if self._tasks:
            return
        self._stop.clear()
        for i in range(self._workers_n):
            self._tasks.append(asyncio.create_task(self._worker_loop(i), name=f"outbox-worker-{i}"))

    async def stop(self, *, drain_timeout: float = 45.0) -> None:
        if not self._tasks:
            return
        self._stop.set()
        deadline = time.monotonic() + drain_timeout
        while time.monotonic() < deadline:
            pending = await self._db.outbox_pending_count()
            if pending == 0:
                break
            await asyncio.sleep(0.2)
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def enqueue_json(
        self,
        *,
        priority: int,
        kind: str,
        payload: dict[str, Any],
        source: str,
        max_attempts: int = 14,
    ) -> int:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        jid = await self._db.outbox_enqueue(
            priority=priority,
            kind=kind,
            payload=raw,
            source=source,
            max_attempts=max_attempts,
        )
        await self._metrics.note_enqueue(1)
        return jid

    async def enqueue_many_json(
        self,
        items: list[tuple[int, str, dict[str, Any], str, int]],
    ) -> list[int]:
        """(priority, kind, payload, source, max_attempts)"""
        rows: list[tuple[int, str, str, str, int]] = []
        for p, k, pl, src, mx in items:
            rows.append((p, k, json.dumps(pl, ensure_ascii=False, separators=(",", ":")), src, mx))
        ids = await self._db.outbox_enqueue_many(rows)
        await self._metrics.note_enqueue(len(ids))
        return ids

    async def _worker_loop(self, idx: int) -> None:
        name = f"outbox-{idx}"
        while not self._stop.is_set():
            try:
                job = await self._db.outbox_claim_one()
                if job is None:
                    await asyncio.sleep(0.03)
                    continue
                jid = int(job["id"])
                kind = str(job["kind"])
                payload = json.loads(str(job["payload"]))
                try:
                    async with self._send_bucket:
                        await self._dispatch(kind, payload, label=f"{name}:{jid}")
                    await self._db.outbox_mark_done(jid)
                    await self._metrics.note_complete(1)
                except Exception as e:
                    st = await self._db.outbox_fail(jid, repr(e))
                    await self._metrics.bump(jobs_retried=1)
                    if st == "dead":
                        await self._metrics.bump(jobs_dead=1)
                        log.error("%s: job %s dead after error %s", name, jid, e, exc_info=True)
                    else:
                        log.warning("%s: job %s will retry: %s", name, jid, e)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("%s: worker crash protection", name)
                await asyncio.sleep(0.5)

    async def _dispatch(self, kind: str, payload: dict[str, Any], *, label: str) -> None:
        if kind == "send_message":
            markup = payload.get("reply_markup_json")
            rm = InlineKeyboardMarkup.model_validate_json(markup) if markup else None
            await call_with_telegram_retry(
                lambda: self._bot.send_message(
                    int(payload["chat_id"]),
                    str(payload["text"]),
                    reply_markup=rm,
                ),
                metrics=self._metrics,
                base_label=label,
            )
            return
        if kind == "send_photo":
            await call_with_telegram_retry(
                lambda: self._bot.send_photo(
                    int(payload["chat_id"]),
                    str(payload["file_id"]),
                    caption=payload.get("caption"),
                ),
                metrics=self._metrics,
                base_label=label,
            )
            return
        if kind == "send_video":
            await call_with_telegram_retry(
                lambda: self._bot.send_video(
                    int(payload["chat_id"]),
                    str(payload["file_id"]),
                    caption=payload.get("caption"),
                ),
                metrics=self._metrics,
                base_label=label,
            )
            return
        if kind == "send_document":
            await call_with_telegram_retry(
                lambda: self._bot.send_document(
                    int(payload["chat_id"]),
                    str(payload["file_id"]),
                    caption=payload.get("caption"),
                ),
                metrics=self._metrics,
                base_label=label,
            )
            return
        if kind == "archive_send":
            await call_with_telegram_retry(
                lambda: self._archive.send(
                    self._bot,
                    str(payload["file_type"]),
                    str(payload["file_id"]),
                    caption=payload.get("caption"),
                ),
                metrics=self._metrics,
                base_label=label + ":archive",
            )
            return
        raise ValueError(f"unknown outbox kind {kind}")
