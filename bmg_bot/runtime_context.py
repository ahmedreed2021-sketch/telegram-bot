from __future__ import annotations

import asyncio
from dataclasses import dataclass

from bmg_bot.config import Settings
from bmg_bot.database import Database
from bmg_bot.metrics import RuntimeMetrics
from bmg_bot.outbound import OutboundHub
from bmg_bot.rate_limit import SlidingWindowCounter, TokenBucket
from bmg_bot.repository import LobbyRepository
from bmg_bot.services.archive import ArchiveService


@dataclass(slots=True)
class RuntimeContext:
    settings: Settings
    db: Database
    repo: LobbyRepository
    archive: ArchiveService
    metrics: RuntimeMetrics
    outbound: OutboundHub
    start_bucket: TokenBucket
    start_sem: asyncio.Semaphore
    global_msg_bucket: TokenBucket
    user_sliding: SlidingWindowCounter
