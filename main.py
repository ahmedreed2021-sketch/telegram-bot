import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery

BOT_TOKEN = '8734604709:AAEyxy0wnIcl3zQVd2vuzlMzZZCheU1OeUc'
OWNER_ID = 8755001668

MAX_USERS = 502

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

users = {}
pending_users = {}
banned_users = {}

waiting_name = set()

# start
@dp.message(F.text == "/start")
async def start(message: Message):

    user_id = message.from_user.id

    if user_id in banned_users:

        await message.answer(
            f"تم حظرك\nالسبب : {banned_users[user_id]}"
        )

        return

    if user_id in users:

        await message.answer("انت مشترك بالفعل")
        return

    waiting_name.add(user_id)

    await message.answer("ارسل اسم مستعار")


# استقبال الرسائل
@dp.message(~F.text.startswith("/"))
async def all_messages(message: Message):

    user_id = message.from_user.id

    # لو محظور
    if user_id in banned_users:

        await message.answer(
            f"تم حظرك\nالسبب : {banned_users[user_id]}"
        )

        return

    # حفظ الاسم المستعار
    if user_id in waiting_name:

        nickname = message.text

        pending_users[user_id] = nickname

        waiting_name.remove(user_id)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="قبول",
                        callback_data=f"accept_{user_id}"
                    ),

                    InlineKeyboardButton(
                        text="رفض",
                        callback_data=f"reject_{user_id}"
                    )
                ]
            ]
        )

        await bot.send_message(
            OWNER_ID,
            f"طلب انضمام جديد\n\n"
            f"الاسم : {nickname}\n"
            f"الايدي : {user_id}",
            reply_markup=keyboard
        )

        await message.answer(
            "تم ارسال طلب الانضمام انتظر موافقة الإدارة"
        )

        return

    # لو غير مقبول
    if user_id not in users:

        await message.answer(
            "انت غير مقبول حاليا"
        )

        return

    # حذف الرسالة الأصلية
    try:
        await message.delete()
    except:
        pass

    nickname = users[user_id]

    # نشر الرسالة للجميع
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


# قبول / رفض
@dp.callback_query()
async def callbacks(call: CallbackQuery):

    if call.from_user.id != OWNER_ID:
        return

    data = call.data

    # قبول
    if data.startswith("accept_"):

        user_id = int(data.split("_")[1])

        nickname = pending_users[user_id]

        # الحد الأقصى
        if len(users) >= MAX_USERS:

            await bot.send_message(
                user_id,
                "البوت ممتلئ حاليا"
            )

            return

        users[user_id] = nickname

        del pending_users[user_id]

        await bot.send_message(
            user_id,
            "تم قبول طلبك يمكنك النشر الآن"
        )

        await call.message.edit_text(
            f"تم قبول {nickname}"
        )

    # رفض
    elif data.startswith("reject_"):

        user_id = int(data.split("_")[1])

        nickname = pending_users[user_id]

        del pending_users[user_id]

        await bot.send_message(
            user_id,
            "تم رفض طلبك"
        )

        await call.message.edit_text(
            f"تم رفض {nickname}"
        )


# حظر عضو
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
            "تم حظر العضو"
        )

        await bot.send_message(
            user_id,
            f"تم حظرك\nالسبب : {reason}"
        )

    except:

        await message.answer(
            "استخدم:\n/ban id السبب"
        )


# طرد عضو
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
                "تم طردك من البوت"
            )

            await message.answer(
                "تم الطرد"
            )

    except:

        await message.answer(
            "استخدم:\n/kick id"
        )


# عدد الأعضاء
@dp.message(F.text == "/members")
async def members(message: Message):

    if message.from_user.id != OWNER_ID:
        return

    await message.answer(
        f"عدد الاعضاء : {len(users)}"
    )


async def main():
    await dp.start_polling(bot)

asyncio.run(main())