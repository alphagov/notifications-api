import os
import struct
import time
import uuid

from app import current_app, db
from sqlalchemy import text  # type: ignore[reportMissingImports]

ADVISORY_LOCK_ID = struct.unpack(">q", struct.pack("8s", "some-random-string-2".encode()))[0]


LOCK_HOLD_SECONDS = 60


def process_shared_lock(hold_seconds: int = LOCK_HOLD_SECONDS):
    run_id = uuid.uuid4().hex[:8]
    prefix = f"Shared_lock_POC [run_id={run_id} os_pid={os.getpid()}]"

    current_app.logger.info(f"{prefix} started")
    current_app.logger.info(f"{prefix} DB backend pid: {_get_backend_pid()} (same value across runs => shared connection)")
    current_app.logger.info(f"{prefix} Lock ID being used: {ADVISORY_LOCK_ID}")

    lock_acquired = _try_advisory_lock(ADVISORY_LOCK_ID)
    current_app.logger.info(f"{prefix} Lock acquired: {lock_acquired}")

    if not lock_acquired:
        current_app.logger.warning(f"{prefix} Failed to acquire shared lock, exiting")
        return False

    try:
        current_app.logger.info(f"{prefix} Holding lock for {hold_seconds}s")
        time.sleep(hold_seconds)
    finally:
        released = _release_advisory_lock(ADVISORY_LOCK_ID)
        current_app.logger.info(f"{prefix} Lock released: {released}")

    current_app.logger.info(f"{prefix} finished")
    return True


def _get_backend_pid() -> int:
    return db.session.execute(text("SELECT pg_backend_pid()")).scalar()


def _try_advisory_lock(lock_id: int) -> bool:
    sql = text("SELECT pg_try_advisory_lock(:lock_id)")
    return bool(db.session.execute(sql, {"lock_id": lock_id}).scalar())


def _release_advisory_lock(lock_id: int) -> bool:
    sql = text("SELECT pg_advisory_unlock(:lock_id)")
    return bool(db.session.execute(sql, {"lock_id": lock_id}).scalar())
