# total=False to make all keys optional by default, except those marked as Required
import struct
from typing import Required, TypedDict
from flask import current_app
from sqlalchemy import text  # type: ignore[reportMissingImports]
from app import db

REPLICATION_SLOT_NAME = "notify_wal2json_slot"
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
# Use the first eight bytes of the slot name as a deterministic signed 64-bit advisory lock ID.
# This is inline with the way we build lock IDs for advisory locks for database migrations.
REPLICATION_ADVISORY_LOCK_ID = struct.unpack(">q", struct.pack("8s", REPLICATION_SLOT_NAME.encode()))[0]


class ReplicationSlotChangesResult(TypedDict, total=False):
    lock_acquired: Required[bool]
    slot_name: str
    upto_nchanges: int
    changes_count: int
    processed_changes: int
    ignored_changes: int
    service_stats_change_count_buckets: int
    last_lsn: str | None


def dao_process_notifications_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
) -> ReplicationSlotChangesResult:
    lock_acquired = False

    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)

        if not lock_acquired:
            return {
                "lock_acquired": lock_acquired,
                "slot_name": slot_name,
                "upto_nchanges": upto_nchanges,
            }

    except Exception:
        current_app.logger.exception("Failed to process replication slot changes")
        raise

    finally:
        if lock_acquired:
            try:
                _advisory_unlock(advisory_lock_id)
            except Exception:
                current_app.logger.exception("Failed to release advisory lock")
                raise


def _try_advisory_lock(lock_id: int) -> bool:
    sql = text("SELECT pg_try_advisory_lock(:lock_id)")
    return bool(db.session.execute(sql, {"lock_id": lock_id}).scalar())


def _advisory_unlock(lock_id: int) -> None:
    db.session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
