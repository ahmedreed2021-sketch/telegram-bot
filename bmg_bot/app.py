from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import ErrorEvent

from bmg_bot.config import Settings, load_settings
from bmg_bot.database import Database
from bmg_bot.handlers import admin, callbacks, users
from bmg_bot.metrics import RuntimeMetrics
from bmg_bot.middlewares import (
    AdvancedRateLimitMiddleware,
    EventCountMiddleware,
    RepoMiddleware,
    StartJoinGateMiddleware,
)
from bmg_bot.outbound import OutboundHub
from bmg_bot.rate_limit import SlidingWindowCounter, TokenBucket
from bmg_bot.repository import LobbyRepository
from bmg_bot.restore import restore_sqlite_if_requested
from bmg_bot.runtime_context import RuntimeContext
from bmg_bot.services.archive import ArchiveService
from bmg_bot.services.backup import run_backup_loop
from bmg_bot.services.inactivity import inactivity_watch_loop
from bmg_bot.services.maintenance import maintenance_loop

log = logging.getLogger(__name__)


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_dispatcher(ctx: RuntimeContext) -> Dispatcher:
    dp = Dispatcher()

    @dp.errors()
    async def on_error(event: ErrorEvent) -> None:
        from aiogram.exceptions import TelegramBadRequest

        if isinstance(event.exception, TelegramBadRequest):
            log.warning("Telegram API (non-fatal): %s", event.exception)
            return
        await ctx.metrics.bump(handler_errors=1)
        log.exception(
            "Update handler failed: %s | update_id=%s",
            event.exception,
            event.update.update_id if event.update else None,
        )

    dp.message.outer_middleware(RepoMiddleware(ctx))
    dp.message.outer_middleware(EventCountMiddleware(ctx))
    dp.message.outer_middleware(StartJoinGateMiddleware(ctx))
    dp.message.outer_middleware(AdvancedRateLimitMiddleware(ctx))

    dp.callback_query.outer_middleware(RepoMiddleware(ctx))
    dp.callback_query.outer_middleware(EventCountMiddleware(ctx))
    dp.callback_query.outer_middleware(AdvancedRateLimitMiddleware(ctx))

    dp.include_router(admin.router)
    dp.include_router(callbacks.router)
    dp.include_router(users.router)
    return dp


async def _health_handler(request: web.Request) -> web.Response:
    ctx: RuntimeContext = request.app["ctx"]
    snap = await ctx.metrics.snapshot()
    pending = await ctx.db.outbox_pending_count()
    body = {
        "status": "ok",
        "outbox_pending": pending,
        "metrics": snap,
    }
    return web.json_response(body, dumps=lambda obj: json.dumps(obj, default=str))


async def _health_app(ctx: RuntimeContext) -> web.Application:
    app = web.Application()
    app["ctx"] = ctx
    app.router.add_get("/health", _health_handler)
    return app


async def run() -> None:
    setup_logging()
    settings = load_settings()
    restore_sqlite_if_requested(target_db_path=settings.sqlite_path)

    metrics = RuntimeMetrics()
    db = Database(settings.sqlite_path)
    await db.connect()
    repo = LobbyRepository(db)
    await repo.load_from_db()

    archive = ArchiveService(db, settings.archive_channel_ids)
    await archive.load_state()

    session = AiohttpSession(limit=settings.aiohttp_connector_limit)
    bot = Bot(settings.bot_token, session=session)

    outbound = OutboundHub(
        db=db,
        bot=bot,
        metrics=metrics,
        archive=archive,
        workers=settings.outbox_workers,
        global_send_bucket=settings.outbound_global_send_limit,
    )

    start_bucket = TokenBucket(
        capacity=settings.start_bucket_capacity,
        refill_per_sec=settings.start_bucket_refill_per_sec,
    )
    start_sem = asyncio.Semaphore(settings.start_concurrency)
    global_msg_bucket = TokenBucket(
        capacity=settings.global_msg_bucket_capacity,
        refill_per_sec=settings.global_msg_refill_per_sec,
    )
    user_sliding = SlidingWindowCounter(
        window_sec=settings.sliding_window_sec,
        max_entries_per_key=256,
    )

    ctx = RuntimeContext(
        settings=settings,
        db=db,
        repo=repo,
        archive=archive,
        metrics=metrics,
        outbound=outbound,
        start_bucket=start_bucket,
        start_sem=start_sem,
        global_msg_bucket=global_msg_bucket,
        user_sliding=user_sliding,
    )

    outbound.start()
    dp = build_dispatcher(ctx)

    @dp.shutdown.register
    async def _drain_outbox(**_: Any) -> None:
        log.info("Shutdown: draining outbound queue…")
        await outbound.stop(drain_timeout=55.0)

    bg_tasks: list[asyncio.Task[Any]] = []

    if settings.backup_interval_seconds > 0:
        os.makedirs(settings.backup_dir, exist_ok=True)
        bg_tasks.append(
            asyncio.create_task(
                run_backup_loop(
                    db_path=settings.sqlite_path,
                    backup_dir=settings.backup_dir,
                    interval_seconds=settings.backup_interval_seconds,
                    keep=settings.backup_keep,
                ),
                name="backup",
            )
        )

    bg_tasks.append(
        asyncio.create_task(inactivity_watch_loop(bot, repo), name="inactivity"),
    )

    bg_tasks.append(
        asyncio.create_task(
            maintenance_loop(
                db=db,
                metrics=metrics,
                interval_sec=settings.cleanup_interval_sec,
                outbox_done_retention_sec=settings.outbox_done_retention_sec,
            ),
            name="maintenance",
        ),
    )

    runner: web.AppRunner | None = None
    site: web.TCPSite | None = None
    if settings.health_check:
        port = int(os.getenv("PORT", "8080"))
        runner = web.AppRunner(await _health_app(ctx))
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=port)
        await site.start()
        log.info("Health JSON on 0.0.0.0:%s/health", port)

    log.info(
        "BMG bot polling (sqlite=%s outbox_workers=%s update_concurrency=%s)",
        settings.sqlite_path,
        settings.outbox_workers,
        settings.update_tasks_concurrency,
    )

    try:
        await dp.start_polling(
            bot,
            handle_as_tasks=True,
            tasks_concurrency_limit=settings.update_tasks_concurrency,
        )
    finally:
        for t in bg_tasks:
            t.cancel()
        if bg_tasks:
            await asyncio.gather(*bg_tasks, return_exceptions=True)
        if site:
            await site.stop()
        if runner:
            await runner.cleanup()
        await outbound.stop(drain_timeout=8.0)
        await db.close()
