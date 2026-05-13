from __future__ import annotations

import asyncio
import logging

from bmg_bot.database import Database
from bmg_bot.metrics import RuntimeMetrics

log = logging.getLogger(__name__)


async def maintenance_loop(
    *,
    db: Database,
    metrics: RuntimeMetrics,
    interval_sec: int,
    outbox_done_retention_sec: int,
) -> None:
    while True:
        try:
            await asyncio.sleep(interval_sec)
            deleted = await db.outbox_cleanup_done(older_than_sec=outbox_done_retention_sec)
            pruned = await db.join_throttle_prune(older_than_sec=86400)
            pending = await db.outbox_pending_count()
            await metrics.set_queue_depth_hint(pending)
            if deleted or pruned:
                log.info("Maintenance: removed %s done outbox rows, %s join throttle rows", deleted, pruned)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Maintenance loop error")
