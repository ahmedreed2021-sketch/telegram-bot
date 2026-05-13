from __future__ import annotations

import logging

from typing import Any

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bmg_bot.config import Settings
from bmg_bot.metrics import RuntimeMetrics
from bmg_bot.outbound import JobPriority, OutboundHub
from bmg_bot.repository import LobbyRepository
from bmg_bot.telegram_safe import call_with_telegram_retry

log = logging.getLogger(__name__)

router = Router(name="callbacks")


@router.callback_query()
async def callbacks(
    call: CallbackQuery,
    repo: LobbyRepository,
    settings: Settings,
    outbound: OutboundHub,
    metrics: RuntimeMetrics,
) -> None:
    if not call.from_user or not call.data or not call.message:
        await call_with_telegram_retry(lambda: call.answer(), metrics=metrics, base_label="cb_empty")
        return

    if not settings.is_admin(call.from_user.id):
        await call_with_telegram_retry(
            lambda: call.answer("Not allowed.", show_alert=True),
            metrics=metrics,
            base_label="cb_denied",
        )
        return

    data = call.data

    try:
        if data.startswith("accept_"):
            user_id = int(data.removeprefix("accept_"))
            pending = repo.pending_users.get(user_id)
            if not pending:
                await call_with_telegram_retry(
                    lambda: call.answer("Submission no longer pending.", show_alert=True),
                    metrics=metrics,
                    base_label="cb_nopending",
                )
                return
            nickname = pending.alias
            if len(repo.users) >= settings.max_users:
                await outbound.enqueue_json(
                    priority=JobPriority.ADMIN,
                    kind="send_message",
                    payload={"chat_id": user_id, "text": "⛔ Lobby is full."},
                    source="accept_full",
                )
                await call_with_telegram_retry(
                    lambda: call.answer("Lobby is full.", show_alert=True),
                    metrics=metrics,
                    base_label="cb_full",
                )
                return
            await repo.approve_user(user_id, nickname)
            await outbound.enqueue_json(
                priority=JobPriority.ADMIN,
                kind="send_message",
                payload={"chat_id": user_id, "text": "✅ Your request has been approved."},
                source="accept_ok",
            )
            await call_with_telegram_retry(
                lambda: call.message.edit_text(f"✅ Accepted {nickname}"),
                metrics=metrics,
                base_label="cb_edit_accept",
            )
            await call_with_telegram_retry(lambda: call.answer(), metrics=metrics, base_label="cb_ok")
            return

        if data.startswith("reject_"):
            user_id = int(data.removeprefix("reject_"))
            pending = repo.pending_users.get(user_id)
            nickname = pending.alias if pending else str(user_id)
            await repo.delete_pending(user_id)
            await outbound.enqueue_json(
                priority=JobPriority.ADMIN,
                kind="send_message",
                payload={"chat_id": user_id, "text": "❌ Your request has been rejected."},
                source="reject",
            )
            await call_with_telegram_retry(
                lambda: call.message.edit_text(f"❌ Rejected {nickname}"),
                metrics=metrics,
                base_label="cb_edit_reject",
            )
            await call_with_telegram_retry(lambda: call.answer(), metrics=metrics, base_label="cb_ok")
            return
    except Exception:
        log.exception("Callback handling failed data=%s", data)
        await call_with_telegram_retry(
            lambda: call.answer("Error processing action.", show_alert=True),
            metrics=metrics,
            base_label="cb_err",
        )
        return

    await call_with_telegram_retry(lambda: call.answer(), metrics=metrics, base_label="cb_fallback")
