from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

log = logging.getLogger(__name__)


async def run_backup_loop(
    *,
    db_path: str,
    backup_dir: str,
    interval_seconds: int,
    keep: int,
) -> None:
    if interval_seconds <= 0:
        return
    dest_root = Path(backup_dir)
    dest_root.mkdir(parents=True, exist_ok=True)
    src = Path(db_path)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            if not src.is_file():
                continue
            stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
            target = dest_root / f"bmg-{stamp}.db"
            await asyncio.to_thread(shutil.copy2, src, target)
            manifest = dest_root / "last_backup.json"
            try:
                import json
                import time as time_mod

                manifest.write_text(
                    json.dumps(
                        {"path": str(target), "ts": time_mod.time(), "source_db": str(src)},
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError:
                log.warning("Could not write backup manifest")
            files = sorted(dest_root.glob("bmg-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in files[keep:]:
                try:
                    old.unlink(missing_ok=True)
                except OSError:
                    log.warning("Could not remove old backup %s", old)
            log.info("Database backup written to %s", target)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Backup loop error")
