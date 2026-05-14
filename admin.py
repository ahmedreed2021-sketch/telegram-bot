from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from config import OWNER_ID

router = Router()


# =========================
# CHECK ADMIN
# =========================

def is_admin(user_id):
    return user_id == OWNER_ID


# =========================
# ADMIN PANEL
# =========================

@router.message(Command("admin"))
async def admin_panel(message: Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
    "⚙️ ADMIN PANEL\n\n"
    "👥 /stats - Statistics\n"
    "🚫 /ban - Ban User\n"
    "⚠️ /warn - Warn User\n"
    "🔇 /mute - Mute User\n"
    "🔊 /unmute - Unmute User\n"
    "📢 /broadcast - Broadcast Message\n"
    "🛡️ System Online"
)


# =========================
# BAN
# =========================

@router.message(Command("ban"))
async def ban_user(message: Message):

    if not is_admin(message.from_user.id):
        return

    args = message.text.split()

    if len(args) < 2:
        await message.answer("Usage: /ban USER_ID")
        return

    user_id = int(args[1])

    await message.answer(
        f"🚫 User {user_id} banned"
    )


# =========================
# WARN
# =========================

@router.message(Command("warn"))
async def warn_user(message: Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "⚠️ Warn command works"
    )


# =========================
# MUTE
# =========================

@router.message(Command("mute"))
async def mute_user(message: Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🔇 Mute command works"
    )


# =========================
# UNMUTE
# =========================

@router.message(Command("unmute"))
async def unmute_user(message: Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🔊 Unmute command works"
    )


# =========================
# STATS
# =========================

@router.message(Command("stats"))
async def stats(message: Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "📊 Stats command works"
    )