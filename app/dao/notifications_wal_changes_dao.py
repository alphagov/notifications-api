# total=False to make all keys optional by default, except those marked as Required
import struct
from typing import Required, TypedDict

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
    pass
