from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from bmg_bot.config import Settings
from bmg_bot.metrics import RuntimeMetrics
from bmg_bot.outbound import JobPriority, OutboundHub
from bmg_bot.repository import LobbyRepository
from bmg_bot.telegram_safe import call_with_telegram_retry

log = logging.getLogger(__name__)

router = Router(name="admin")


@router.message(F.text.startswith("/ban"))
async def ban_user(
    message: Message,
    repo: LobbyRepository,
    settings: Settings,
    outbound: OutboundHub,
    metrics: RuntimeMetrics,
) -> None:
    if not message.from_user or not settings.is_admin(message.from_user.id):
        return
    try:
        parts = (message.text or "").split()
        user_id = int(parts[1])
        reason = " ".join(parts[2:]) if len(parts) > 2 else "No reason given"
        await repo.ban_user(user_id, reason)
        await call_with_telegram_retry(
            lambda: message.answer("✅ User banned."),
            metrics=metrics,
            base_label="ban_ok",
        )
        await outbound.enqueue_json(
            priority=JobPriority.ADMIN,
            kind="send_message",
            payload={"chat_id": user_id, "text": f"⛔ You are banned\nReason: {reason}"},
            source="ban_notify",
        )
    except (IndexError, ValueError):
        await call_with_telegram_retry(
            lambda: message.answer("Usage:\n/ban id reason"),
            metrics=metrics,
            base_label="ban_usage",
        )


@router.message(F.text.startswith("/kick"))
async def kick(
    message: Message,
    repo: LobbyRepository,
    settings: Settings,
    outbound: OutboundHub,
    metrics: RuntimeMetrics,
) -> None:
    if not message.from_user or not settings.is_admin(message.from_user.id):
        return
    try:
        user_id = int((message.text or "").split()[1])
        if user_id in repo.users:
            await repo.remove_user(user_id)
            await outbound.enqueue_json(
                priority=JobPriority.ADMIN,
                kind="send_message",
                payload={"chat_id": user_id, "text": "❌ You have been kicked."},
                source="kick_notify",
            )
            await call_with_telegram_retry(
                lambda: message.answer("✅ User kicked."),
                metrics=metrics,
                base_label="kick_ok",
            )
        else:
            await call_with_telegram_retry(
                lambda: message.answer("User is not an approved member."),
                metrics=metrics,
                base_label="kick_noop",
            )
    except (IndexError, ValueError):
        await call_with_telegram_retry(
            lambda: message.answer("Usage:\n/kick id"),
            metrics=metrics,
            base_label="kick_usage",
        )


@router.message(F.text == "/members")
async def members(
    message: Message,
    repo: LobbyRepository,
    settings: Settings,
    metrics: RuntimeMetrics,
) -> None:
    if not message.from_user or not settings.is_admin(message.from_user.id):
        return
    await call_with_telegram_retry(
        lambda: message.answer(f"👥 Members: {len(repo.users)}"),
        metrics=metrics,
        base_label="members",
    )


@router.message(F.text == "/panel")
async def panel(
    message: Message,
    repo: LobbyRepository,
    settings: Settings,
    metrics: RuntimeMetrics,
) -> None:
    if not message.from_user or not settings.is_admin(message.from_user.id):
        return
    if not repo.users:
        await call_with_telegram_retry(
            lambda: message.answer("❌ No members."),
            metrics=metrics,
            base_label="panel_empty",
        )
        return
    chunks: list[str] = []
    buf = "👥 MEMBERS PANEL\n\n"
    for uid, nickname in repo.users.items():
        stats = repo.user_stats.get(uid)
        photos = stats.photos if stats else 0
        videos = stats.videos if stats else 0
        documents = stats.documents if stats else 0
        messages_c = stats.messages if stats else 0
        warns = stats.warns if stats else 0
        total_media = photos + videos + documents
        status = "🟢" if total_media > 0 else "🔴"
        block = (
            f"{status} {nickname}\n"
            f"🆔 {uid}\n"
            f"📩 {messages_c}\n"
            f"🖼 {photos}\n"
            f"🎥 {videos}\n"
            f"📄 {documents}\n"
            f"⚠️ {warns}\n\n"
        )
        if len(buf) + len(block) > 4000:
            chunks.append(buf)
            buf = block
        else:
            buf += block
    chunks.append(buf)
    for part in chunks:
        await call_with_telegram_retry(
            lambda p=part: message.answer(p),
            metrics=metrics,
            base_label="panel_chunk",
        )
