from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
import asyncio
import aiosqlite

BOT_TOKEN = "8734604709:AAEyxy0wnIcl3zQVd2vuzlMzZZCheU1OeUc"
OWNER_ID = 8755001668
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

waiting_alias = set()

# ================= DATABASE =================

async def init_db():
    async with aiosqlite.connect("bmg.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            alias TEXT
        )
        """)
        await db.commit()

# ================= START =================

@dp.message(Command("start"))
async def start_command(message: Message):

    user_id = message.from_user.id

    async with aiosqlite.connect("bmg.db") as db:
        cursor = await db.execute(
            "SELECT alias FROM users WHERE user_id = ?",
            (user_id,)
        )
        user = await cursor.fetchone()

    if user:
        await message.answer(
            f"✅ Welcome back!\n\nYour alias: 🔰 {user[0]}"
        )
        return

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

━━━━━━━━━━━━━━

📷 Media rules

• Post cool stuff, not spam dumps
• No weird illegal stuff

━━━━━━━━━━━━━━

💬 Chat energy

• Say hi when you join or lose XP 🎮
• Drama belongs in reality TV, not here
• Flirting allowed, being creepy = nope 🚫

━━━━━━━━━━━━━━

⚠️ Admin powers

Mods can:
• bonk 🪄
• mute 🤐
• yeet 🚀

⛔️ THIS IS A BOY ONLY GROUP.
IF YOU SEND IMAGES OF GIRLS YOU WILL BE PERMANENTLY BANNED.

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

    waiting_alias.add(user_id)

# ================= HELP =================

@dp.message(Command("help"))
async def help_command(message: Message):

    text = """
📚 BMG 2026 Help

💬 HOW IT WORKS
• Messages are relayed anonymously to all members
• Your alias and rank emoji are shown instead of your name
• Rank-based quotas and perks reward active members

━━━━━━━━━━━━━━

⚡ Basic Commands

/start - Start or restart the bot
/help - Show this help menu
/stats - View your statistics and rank
/perks - View all rank tiers and benefits
/leaderboard - View top contributors
/alias - Change your display name
/version - Show bot version
/test - Check connection status

━━━━━━━━━━━━━━

👥 Social Commands

/block <alias> - Block/unblock a user
/flag [reason] - Report content

━━━━━━━━━━━━━━

🏆 Rank System

12 Rank Tiers:
🟩 Newcomer → 🥉 Bronze → 🥈 Silver
🥇 Gold → 🏆 Platinum → 💎 Diamond
👑 Master → ⭐ Legend → 🌟 Mythic

━━━━━━━━━━━━━━

📜 Info Commands

/rules - View lobby rules
/welcome - View welcome message
/leave - Leave the lobby

━━━━━━━━━━━━━━

📦 Archive Commands

/archive - Browse archives
/purchases - View purchases

━━━━━━━━━━━━━━

🧵 Topics

/blocktopic - Mute/unmute topic
/resynctopics - Recreate topics

━━━━━━━━━━━━━━

⚠️ This is a BOYS ONLY lobby.
"""

    await message.answer(text)

# ================= SAVE ALIAS =================

@dp.message()
async def save_alias(message: Message):

    user_id = message.from_user.id

    if user_id not in waiting_alias:
        return

    alias = message.text.strip()

    if len(alias) < 3 or len(alias) > 24:
        await message.answer(
            "❌ Alias must be between 3 and 24 characters."
        )
        return

    async with aiosqlite.connect("bmg.db") as db:

        cursor = await db.execute(
            "SELECT alias FROM users WHERE alias = ?",
            (alias,)
        )

        existing = await cursor.fetchone()

        if existing:
            await message.answer(
                "❌ This alias is already taken."
            )
            return

        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, alias) VALUES (?, ?)",
            (user_id, alias)
        )

        await db.commit()

    waiting_alias.remove(user_id)

    success_text = f"""
✅ Alias Set!

Your alias: 🔰 {alias}

Next Steps:
📸 Send 3 media items within the next 30 minutes to fully join the lobby.

Media can be:
Photos 🖼️
Videos 🎥
Documents 📄
Audio 🎵
Voice 🎤
Animations 🎞️

Type /help for more information!
"""

    await message.answer(success_text)

# ================= MAIN =================

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())