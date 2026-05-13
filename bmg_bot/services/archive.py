from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot

    from bmg_bot.database import Database

log = logging.getLogger(__name__)

KV_INDEX = "archive_channel_index"
KV_COUNTER = "archive_channel_counter"


class ArchiveService:
    def __init__(self, db: Database, channel_ids: tuple[int, ...]) -> None:
        self.db = db
        self.channel_ids = channel_ids
        self._index = 0
        self._counter = 0

    async def load_state(self) -> None:
        raw_i = await self.db.get_kv(KV_INDEX)
        raw_c = await self.db.get_kv(KV_COUNTER)
        try:
            self._index = int(raw_i) if raw_i is not None else 0
        except ValueError:
            self._index = 0
        try:
            self._counter = int(raw_c) if raw_c is not None else 0
        except ValueError:
            self._counter = 0
        if not self.channel_ids:
            self._index = 0
            self._counter = 0

    async def _persist(self) -> None:
        await self.db.set_kv(KV_INDEX, str(self._index))
        await self.db.set_kv(KV_COUNTER, str(self._counter))

    def _advance_rotation(self) -> None:
        if not self.channel_ids:
            return
        self._counter += 1
        if self._counter >= 100:
            self._counter = 0
            self._index += 1
            if self._index >= len(self.channel_ids):
                self._index = 0

    async def send(
        self,
        bot: Bot,
        file_type: str,
        file_id: str,
        caption: str | None = None,
    ) -> None:
        if not self.channel_ids:
            return
        channel_id = self.channel_ids[self._index]
        try:
            if file_type == "photo":
                await bot.send_photo(channel_id, file_id, caption=caption)
            elif file_type == "video":
                await bot.send_video(channel_id, file_id, caption=caption)
            elif file_type == "document":
                await bot.send_document(channel_id, file_id, caption=caption)
            else:
                return
            self._advance_rotation()
            await self._persist()
        except Exception:
            log.exception("Archive send failed channel=%s type=%s", channel_id, file_type)
            raise
