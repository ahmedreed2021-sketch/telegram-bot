import aiosqlite

DB_NAME = "/data/bot2.db"


async def init_db():

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            alias TEXT,
            approved INTEGER DEFAULT 0,
            media_count INTEGER DEFAULT 0,
            weekly_media INTEGER DEFAULT 0,
            warns INTEGER DEFAULT 0
        )
        """)

        await db.commit()


async def add_user(user_id, alias):

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute(
            """
            INSERT OR REPLACE INTO users
            (user_id, alias)
            VALUES (?, ?)
            """,
            (user_id, alias)
        )

        await db.commit()


async def add_media(user_id):

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute(
            """
            UPDATE users
            SET media_count = media_count + 1
            WHERE user_id = ?
            """,
            (user_id,)
        )

        await db.commit()


async def approve_user(user_id):

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute(
            """
            UPDATE users
            SET approved = 1
            WHERE user_id = ?
            """,
            (user_id,)
        )

        await db.commit()


async def get_user(user_id):

    async with aiosqlite.connect(DB_NAME) as db:

        cursor = await db.execute(
            """
            SELECT * FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )

        return await cursor.fetchone()