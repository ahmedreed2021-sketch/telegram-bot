import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery

BOT_TOKEN = "8734604709:AAEyxy0wnIcl3zQVd2vuzlMzZZCheU1OeUc"

OWNER_ID = 8755001668
MAX_USERS = 502

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

users = {}
pending_users = {}
banned_users = {}

waiting_name = set()

# START
@dp.message(F.text == "/start")
async def start(message: Message):

    user_id = message.from_user.id

    if user_id in banned_users:

        await message.answer(
            f"⛔ You are banned\nReason: {banned_users[user_id]}"
        )

        return

    if user_id in users:

        await message.answer("✅ You are already approved.")
        return

    waiting_name.add(user_id)

    rules_text = """
📜 Lobby Rules

⭐ ⭐️ 🚨 OMG NEW HUMAN 🚨
- just spawned in BMG!!
PLEASE ENSURE ALL SUBMISSIONS ARE 14+
Say hi or we assume you’re a potato 🥔

Also u might wanna read rules. We assume u can read ofc 🤭😬😭🥀

1A - Strictly OVER 14 and BOYS only
1B - IF U dont post minimum 3 times in 7 days you will be banned by the bot.

Welcome to BMG 👋

Yes… you survived the invite. Don’t mess it up.

😂 Basic braincell rules

• Be nice or go touch grass 🌱
• No fighting — this is a group, not WWE
• Respect vibes = stay alive

⸻

📷 Media rules

• Post cool stuff, not spam dumps
• No weird illegal stuff (mods have superpowers)

⸻

💬 Chat energy

• Say hi when you join or lose XP 🎮
• Drama belongs in reality TV, not here
• Flirting allowed, being creepy = nope 🚫

⸻

⚠️ Admin powers

Mods can:
• bonk 🪄
• mute 🤐
• yeet 🚀

⛔ THIS IS A BOY ONLY GROUP, IF YOU SEND IMAGES OF GIRLS YOU WILL BE PERMANENTLY BANNED WITH NO SECOND CHANCES ⛔

Violations may result in warnings, kicks, or bans.
"""

    welcome_text = """
🎭 Welcome to BMG 2026!

This is an anonymous lobby where you chat with others using an alias.

Getting Started:
1️⃣ Choose an alias (display name)
2️⃣ 📸 Send 3 media items within 30 minutes for approval
3️⃣ ⏳ Wait for admin approval to start chatting
4️⃣ Send 3 media items per week to stay active

Please choose your alias:
• 3-24 characters
• Must include at least one letter or number
• Can include emoji and spaces
• Must be unique

Send your desired alias now:
"""

    await message.answer(rules_text)
    await message.answer(welcome_text)


# RECEIVE MESSAGES
@dp.message(~F.text.startswith("/"))
async def all_messages(message: Message):

    user_id = message.from_user.id

    # banned check
    if user_id in banned_users:

        await message.answer(
            f"⛔ You are banned\nReason: {banned_users[user_id]}"
        )

        return

    # save alias
    if user_id in waiting_name:

        nickname = message.text

        pending_users[user_id] = nickname

        waiting_name.remove(user_id)

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
            f"📥 New Join Request\n\n"
            f"👤 Alias: {nickname}\n"
            f"🆔 ID: {user_id}",
            reply_markup=keyboard
        )

        await message.answer(
            f"""✅ Alias Set!

Your alias: 🔰 {nickname}

Next Steps:
📸 Send 3 media items within the next 30 minutes to fully join the lobby.

Media can be:
Photos 🖼️
Videos 🎥
Documents 📄
Audio 🎵
Voice 🎤
Animations 🎞️

Type /help for more information!"""
        )

        return

    # not approved
    if user_id not in users:

        await message.answer(
            "⏳ You are not approved yet."
        )

        return

    # delete original message
    try:
        await message.delete()
    except:
        pass

    nickname = users[user_id]

    # send to everyone
    for uid in users:

        try:

            if message.text:

                await bot.send_message(
                    uid,
                    f"👤 {nickname}\n\n📩 {message.text}"
                )

            elif message.photo:

                await bot.send_photo(
                    uid,
                    message.photo[-1].file_id,
                    caption=f"👤 {nickname}"
                )

            elif message.video:

                await bot.send_video(
                    uid,
                    message.video.file_id,
                    caption=f"👤 {nickname}"
                )

            elif message.document:

                await bot.send_document(
                    uid,
                    message.document.file_id,
                    caption=f"👤 {nickname}"
                )

        except:
            pass


# ACCEPT / REJECT
@dp.callback_query()
async def callbacks(call: CallbackQuery):

    if call.from_user.id != OWNER_ID:
        return

    data = call.data

    # accept
    if data.startswith("accept_"):

        user_id = int(data.split("_")[1])

        nickname = pending_users[user_id]

        if len(users) >= MAX_USERS:

            await bot.send_message(
                user_id,
                "⛔ Lobby is full."
            )

            return

        users[user_id] = nickname

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

        nickname = pending_users[user_id]

        del pending_users[user_id]

        await bot.send_message(
            user_id,
            "❌ Your request has been rejected."
        )

        await call.message.edit_text(
            f"❌ Rejected {nickname}"
        )


# BAN USER
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


# KICK USER
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


# MEMBERS COUNT
@dp.message(F.text == "/members")
async def members(message: Message):

    if message.from_user.id != OWNER_ID:
        return

    await message.answer(
        f"👥 Members: {len(users)}"
    )


async def main():
    await dp.start_polling(bot)

asyncio.run(main())