from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bmg_bot.config import Settings
from bmg_bot.links import text_contains_link
from bmg_bot.metrics import RuntimeMetrics
from bmg_bot.outbound import JobPriority, OutboundHub
from bmg_bot.repository import LobbyRepository
from bmg_bot.telegram_safe import call_with_telegram_retry

router = Router(name="users")


def _not_slash_command(message: Message) -> bool:
    if message.text is None:
        return True
    return not message.text.startswith("/")


async def _safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def _enforce_no_links(message: Message, settings: Settings) -> bool:
    if not message.from_user or settings.is_admin(message.from_user.id):
        return False
    if not message.text:
        return False
    if not text_contains_link(message.text):
        return False
    await _safe_delete(message)
    await call_with_telegram_retry(
        lambda: message.answer("🚫 Links are not allowed."),
        metrics=None,
        base_label="link_block",
    )
    return True


@router.message(F.text == "/start")
async def start(
    message: Message,
    repo: LobbyRepository,
    settings: Settings,
    metrics: RuntimeMetrics,
) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id

    if user_id in repo.banned_users:
        await call_with_telegram_retry(
            lambda: message.answer(f"⛔ You are banned\nReason: {repo.banned_users[user_id]}"),
            metrics=metrics,
            base_label="start_ban",
        )
        return

    if user_id in repo.pending_users:
        await call_with_telegram_retry(
            lambda: message.answer(
                """⏳ Awaiting Approval

Your submission is still pending admin review.
You'll be notified once they approve or reject your submission."""
            ),
            metrics=metrics,
            base_label="start_pending",
        )
        return

    if user_id in repo.users:
        await call_with_telegram_retry(
            lambda: message.answer("✅ You are already approved."),
            metrics=metrics,
            base_label="start_ok",
        )
        return

    await repo.add_waiting_alias(user_id)

    rules_text = """
📜 Lobby Rules

⭐ ⭐️ 🚨 OMG NEW HUMAN 🚨
- just spawned in BMG!!

PLEASE ENSURE ALL SUBMISSIONS ARE 14+

Say hi or we assume you’re a potato 🥔

━━━━━━━━━━━━━━

1A - Strictly OVER 14 and BOYS only

1B - IF U dont post minimum 25 times in 7 days
you will be kicked automatically by the bot.

━━━━━━━━━━━━━━

📷 Media Rules

• No illegal content
• No spam
• No fake media
• No girl content

━━━━━━━━━━━━━━

⚠️ Admin powers

Mods can:
• mute
• warn
• kick
• ban
"""

    welcome_text = """
🎭 Welcome to BMG 2026!

This is an anonymous lobby.

1️⃣ Choose alias
2️⃣ Send 3 media
3️⃣ Wait approval

Send your alias now:
"""

    await call_with_telegram_retry(
        lambda: message.answer(rules_text),
        metrics=metrics,
        base_label="start_rules",
    )
    await call_with_telegram_retry(
        lambda: message.answer(welcome_text),
        metrics=metrics,
        base_label="start_welcome",
    )


@router.message(F.func(_not_slash_command))
async def all_messages(
    message: Message,
    repo: LobbyRepository,
    settings: Settings,
    outbound: OutboundHub,
    metrics: RuntimeMetrics,
) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id

    if await _enforce_no_links(message, settings):
        return

    if user_id in repo.banned_users:
        await call_with_telegram_retry(
            lambda: message.answer(f"⛔ You are banned\nReason: {repo.banned_users[user_id]}"),
            metrics=metrics,
            base_label="msg_ban",
        )
        return

    if user_id in repo.waiting_name:
        if not message.text:
            await call_with_telegram_retry(
                lambda: message.answer("Please send a text alias."),
                metrics=metrics,
                base_label="alias_text",
            )
            return
        nickname = message.text
        await repo.remove_waiting_alias(user_id)
        await repo.set_pending(user_id, nickname)
        await call_with_telegram_retry(
            lambda: message.answer(
                f"""✅ Alias Set!

Your alias: 🔰 {nickname}

📸 Send 3 media items."""
            ),
            metrics=metrics,
            base_label="alias_set",
        )
        return

    if user_id in repo.pending_users:
        if not (message.photo or message.video or message.document):
            return
        await _safe_delete(message)
        count = await repo.bump_pending_media(user_id)
        nickname = repo.pending_users[user_id].alias
        caption = (
            f"📥 New Submission\n\n"
            f"👤 Alias: {nickname}\n"
            f"🆔 ID: {user_id}\n"
            f"📸 Progress: {count}/3"
        )
        batch: list[tuple[int, str, dict[str, Any], str, int]] = []
        for aid in settings.admin_dm_ids():
            if message.photo:
                batch.append(
                    (
                        JobPriority.ADMIN,
                        "send_photo",
                        {"chat_id": aid, "file_id": message.photo[-1].file_id, "caption": caption},
                        "submission",
                        14,
                    )
                )
            elif message.video:
                batch.append(
                    (
                        JobPriority.ADMIN,
                        "send_video",
                        {"chat_id": aid, "file_id": message.video.file_id, "caption": caption},
                        "submission",
                        14,
                    )
                )
            elif message.document:
                batch.append(
                    (
                        JobPriority.ADMIN,
                        "send_document",
                        {"chat_id": aid, "file_id": message.document.file_id, "caption": caption},
                        "submission",
                        14,
                    )
                )
        if batch:
            await outbound.enqueue_many_json(batch)

        await call_with_telegram_retry(
            lambda: message.answer(f"📸 Submission Progress: {count}/3"),
            metrics=metrics,
            base_label="submission_progress",
        )

        if count >= 3:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Accept", callback_data=f"accept_{user_id}"),
                        InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{user_id}"),
                    ]
                ]
            )
            approve_batch: list[tuple[int, str, dict[str, Any], str, int]] = []
            markup_json = keyboard.model_dump_json()
            for aid in settings.admin_dm_ids():
                approve_batch.append(
                    (
                        JobPriority.ADMIN,
                        "send_message",
                        {
                            "chat_id": aid,
                            "text": (
                                f"📥 Approval Request\n\n"
                                f"👤 Alias: {nickname}\n"
                                f"🆔 ID: {user_id}"
                            ),
                            "reply_markup_json": markup_json,
                        },
                        "approval_prompt",
                        14,
                    )
                )
            if approve_batch:
                await outbound.enqueue_many_json(approve_batch)
            await call_with_telegram_retry(
                lambda: message.answer(
                    """⏳ Awaiting Approval

Your submission is still pending admin review."""
                ),
                metrics=metrics,
                base_label="submission_done",
            )
        return

    if user_id not in repo.users:
        await call_with_telegram_retry(
            lambda: message.answer("⚠️ Session expired.\n"
        "Please send /start again."),
            metrics=metrics,
            base_label="not_approved",
        )
        return

    await _safe_delete(message)
    nickname = repo.users[user_id]
    targets = [uid for uid in repo.users]

    items: list[tuple[int, str, dict[str, Any], str, int]] = []

    if message.text:
        await repo.increment_stat(user_id, messages=1, record_activity=True)
        for uid in targets:
            items.append(
                (
                    JobPriority.RELAY,
                    "send_message",
                    {"chat_id": uid, "text": f"👤 {nickname}\n\n📩 {message.text}"},
                    "relay_text",
                    14,
                )
            )
    elif message.photo:
        await repo.increment_stat(user_id, photos=1, record_activity=True)
        items.append(
            (
                JobPriority.ARCHIVE,
                "archive_send",
                {
                    "file_type": "photo",
                    "file_id": message.photo[-1].file_id,
                    "caption": f"👤 {nickname}",
                },
                "relay_archive",
                14,
            )
        )
        for uid in targets:
            items.append(
                (
                    JobPriority.RELAY,
                    "send_photo",
                    {"chat_id": uid, "file_id": message.photo[-1].file_id, "caption": f"👤 {nickname}"},
                    "relay_photo",
                    14,
                )
            )
    elif message.video:
        await repo.increment_stat(user_id, videos=1, record_activity=True)
        items.append(
            (
                JobPriority.ARCHIVE,
                "archive_send",
                {
                    "file_type": "video",
                    "file_id": message.video.file_id,
                    "caption": f"👤 {nickname}",
                },
                "relay_archive",
                14,
            )
        )
        for uid in targets:
            items.append(
                (
                    JobPriority.RELAY,
                    "send_video",
                    {"chat_id": uid, "file_id": message.video.file_id, "caption": f"👤 {nickname}"},
                    "relay_video",
                    14,
                )
            )
    elif message.document:
        await repo.increment_stat(user_id, documents=1, record_activity=True)
        items.append(
            (
                JobPriority.ARCHIVE,
                "archive_send",
                {
                    "file_type": "document",
                    "file_id": message.document.file_id,
                    "caption": f"👤 {nickname}",
                },
                "relay_archive",
                14,
            )
        )
        for uid in targets:
            items.append(
                (
                    JobPriority.RELAY,
                    "send_document",
                    {"chat_id": uid, "file_id": message.document.file_id, "caption": f"👤 {nickname}"},
                    "relay_document",
                    14,
                )
            )
    else:
        return

    if items:
        await outbound.enqueue_many_json(items)
        await metrics.bump(relay_batches=1, relay_messages=len(items))
