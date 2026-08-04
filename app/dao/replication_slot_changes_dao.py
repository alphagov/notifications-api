from flask import current_app
from sqlalchemy import text # type: ignore[reportMissingImports]
from app import db

REPLICATION_SLOT_NAME = "notify_dashboard_replication_slot"
REPLICATION_SLOT_TABLE_NAMES = ("notifications")
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
REPLICATION_ADVISORY_LOCK_ID = 4_009_881

def dao_process_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
) -> dict[str, int | str | bool | None]:
    lock_acquired = False
    current_app.logger.info("-----------------------------------------------------------")
    current_app.logger.info("[STARTED] Replication slot changes")
    current_app.logger.info("-----------------------------------------------------------")

    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)

        if not lock_acquired:
            current_app.logger.info("[SKIPPED] Replication slot changes")
            return {
                "lock_acquired": lock_acquired,
                "slot_name": slot_name,
                "upto_nchanges": upto_nchanges,
            }

        current_app.logger.info(f"[LOCK ACQUIRED] Replication slot changes (lock = {lock_acquired})")
    finally:
        current_app.logger.info(
            f"[RELEASING LOCK] Replication slot changes (lock = {lock_acquired})",
        )
        _advisory_unlock(advisory_lock_id)

    current_app.logger.info("-----------------------------------------------------------")
    current_app.logger.info(f"[FINISHED] Replication slot changes")
    current_app.logger.info("-----------------------------------------------------------")

    return {
        "lock_acquired": lock_acquired,
        "slot_name": slot_name,
        "upto_nchanges": upto_nchanges,
    }

def _try_advisory_lock(lock_id: int) -> bool:
    # The celery beat scheduler runs multiple instances of the same task in parallel,
    # so we need to use an advisory lock to ensure that only one instance of the task is running at a time.
    # Additional check is added to see if the lock is already held by the current process,
    # in which case we don't want to try to acquire it again as there would already be one in progress.
    sql = text("""
        WITH already_held AS (
            SELECT EXISTS (
                SELECT 1
                FROM pg_locks
                WHERE locktype = 'advisory'
                  AND pid = pg_backend_pid()
                  AND granted
                  AND classid = CAST((CAST(:lock_id AS bigint) >> 32) AS integer)
                  AND objid   = CAST((CAST(:lock_id AS bigint) & 4294967295) AS integer)
                  AND objsubid = 1
            ) AS held
        )
        SELECT CASE
                 WHEN held THEN FALSE
                 ELSE pg_try_advisory_lock(:lock_id)
               END
        FROM already_held
    """)
    return bool(db.session.execute(sql, {"lock_id": lock_id}).scalar())

def _advisory_unlock(lock_id: int) -> None:
    db.session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})