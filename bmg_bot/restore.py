from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


def restore_sqlite_if_requested(*, target_db_path: str) -> bool:
    """
    If RESTORE_DB_FROM is set to a path of a .db backup, copy it over the target DB before opening.
    Intended for one-shot Railway / ops recovery (unset after success).
    """
    import os

    src = os.getenv("RESTORE_DB_FROM", "").strip()
    if not src:
        return False
    sp = Path(src)
    if not sp.is_file():
        log.error("RESTORE_DB_FROM points to missing file: %s", src)
        return False
    dest = Path(target_db_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sp, dest)
    log.warning("Restored SQLite database from %s -> %s", sp, dest)
    return True
