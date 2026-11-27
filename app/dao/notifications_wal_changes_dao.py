# total=False to make all keys optional by default, except those marked as Required
import json
import struct
from collections import Counter
from collections.abc import Collection, Container, Iterable, Sequence, Set
from datetime import date, datetime
from time import perf_counter
from typing import NamedTuple, Self, TypedDict

from flask import current_app
from notifications_utils.json import StrictJsonType
from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy import text  # type: ignore[reportMissingImports]

from app import db
from app.dao.fact_notification_status_live_dao import (
    NotificationStatusLiveDimensions,
    upsert_notification_status_live_counts,
)


class TableName(NamedTuple):
    schema: str
    table: str

    def __str__(self):
        return f"{self.schema}.{self.table}"


REPLICATION_SLOT_NAME: str = "notify_wal2json_slot"
REPLICATION_SLOT_UPTO_NCHANGES: int = 10_000

# We want to ignore "insert" changes on certain tables.
# Because "delete" changes don't include enough information to be able to identify the
# correct aggregation bucket, we can't use them to "properly" track the movement of
# notifications to the notification_history table as they hit their retention period
# and get archived. so instead, we'll have to ignore the whole archiving process by
# also ignoring their inserts into notification_history and just *trust* that it all
# works like magic - nothing gets inserted to notification_history that didn't come
# from notifications, no rows get changed as they are moved, etc.
REPLICATION_SLOT_INSERT_TABLE_NAMES: Set[TableName] = frozenset((TableName("public", "notifications"),))
REPLICATION_SLOT_UPDATE_TABLE_NAMES: Set[TableName] = frozenset(
    (TableName("public", "notifications"), TableName("public", "notification_history"))
)
REPLICATION_SLOT_KEY_TYPES: Set[str] = frozenset(
    (
        "normal",
        "team",
    )
)

# Use the first eight bytes of the slot name as a deterministic signed 64-bit advisory lock ID.
# This is inline with the way we build lock IDs for advisory locks for database migrations.
REPLICATION_ADVISORY_LOCK_ID = struct.unpack(">q", struct.pack("8s", REPLICATION_SLOT_NAME.encode()))[0]


class _NameValueDict(TypedDict):
    name: str
    value: StrictJsonType


# This must remain a hashable tuple for use as a Counter key.
# NotificationStatusLiveDimensions is a TypedDict, so use a tuple as the Counter key.
class FullDimensions(NamedTuple):
    bst_date: date
    notification_type: str
    key_type: str
    notification_status: str

    # avoid parsing UUIDs
    service_id: str
    template_id: str

    # Notifications without a job (e.g. sent via the API) are bucketed under a zero UUID, as job_id is part of the
    # primary key of ft_notification_status_live (same convention as ft_notification_status).
    job_id: str = "00000000-0000-0000-0000-000000000000"

    @classmethod
    def _from_columns(cls, columns: Sequence[_NameValueDict]) -> Self:
        d = {
            elem["name"]: elem["value"]
            for elem in columns
            if elem["value"] is not None  # can't have nulls as these all become part of a primary key
            and elem["name"] in cls._fields_and_created_at_set  # type: ignore[attr-defined]
        }
        # special handling only for created_at -> bst_date
        d["bst_date"] = convert_utc_to_bst(datetime.fromisoformat(d.pop("created_at").replace("Z", "+00:00"))).date()
        return cls(**d)

    def _replace_from_columns(self, columns: Sequence[_NameValueDict]) -> Self:
        return self._replace(
            **{
                elem["name"]: elem["value"]
                for elem in columns
                if elem["name"] in self._fields_set  # type: ignore[attr-defined]
            }
        )


# no typing for these because NamedTuple doesn't understand ClassVar
FullDimensions._fields_set = frozenset(FullDimensions._fields)  # type: ignore[attr-defined]
FullDimensions._fields_and_created_at_set = frozenset(FullDimensions._fields + ("created_at",))  # type: ignore[attr-defined]


class ProcessNotificationsReplicationSlotChangesResult(NamedTuple):
    change_count_buckets: int
    advanced_to_lsn: str | None
    raw_change_rows: int
    counted_inserts: int
    counted_updates: int
    ignored_inserts: int
    ignored_updates: int
    ignored_deletes: int
    applied_upserts: int


class LockNotAcquired(RuntimeError):
    pass


def dao_process_notifications_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
    insert_table_names: Set[TableName] = REPLICATION_SLOT_INSERT_TABLE_NAMES,
    update_table_names: Set[TableName] = REPLICATION_SLOT_UPDATE_TABLE_NAMES,
    key_types: Container[str] = REPLICATION_SLOT_KEY_TYPES,
) -> ProcessNotificationsReplicationSlotChangesResult:
    start_time = perf_counter()
    lock_acquired = False
    extra: dict[str, StrictJsonType]

    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)

        if not lock_acquired:
            raise LockNotAcquired(f"Couldn't claim advisory lock {advisory_lock_id!r}")

        # lock acquired, proceed to fetch and process replication slot changes.
        # The batch-level SQL LSN is authoritative when deciding where to advance the replication slot,
        # because we may receive trailing WAL rows for other tables in the same logical slot.
        change_counter_result = _build_change_counter(
            _get_raw_replication_change_rows(
                slot_name=slot_name,
                upto_nchanges=upto_nchanges,
                table_names=insert_table_names | update_table_names,
            ),
            insert_table_names=insert_table_names,
            update_table_names=update_table_names,
            key_types=key_types,
        )

        applied_upserts = 0
        if change_counter_result.change_counter:
            # if we have changes but no last SQL LSN, something went wrong and we should raise an error
            # instead of proceeding to upsert the database and then be unable to advance the slot to
            # register these changes as applied.
            if not change_counter_result.advanceable_lsn:
                raise ValueError(
                    f"No advanceable_lsn found after processing replication slot changes, \
                    replication slot {slot_name} will not be advanced. This should not happen under normal \
                    circumstances."
                )

            # Process the fetched replication slot changes to update service statistics.
            applied_upserts = _upsert_notification_status_live_count(change_counter_result.change_counter)

        if change_counter_result.advanceable_lsn:
            # Advance the replication slot to the last processed SQL LSN
            # to avoid reprocessing the same changes in future runs.
            extra = {
                "slot_name": slot_name,
                "advanceable_lsn": change_counter_result.advanceable_lsn,
            }
            current_app.logger.debug(
                "Advancing replication slot %(slot_name)r to advanceable_lsn=%(advanceable_lsn)s",
                extra,
                extra=extra,
            )
            _advance_replication_slot(change_counter_result.advanceable_lsn, slot_name=slot_name)

        extra = {
            "slot_name": slot_name,
            "advanced_to_lsn": change_counter_result.advanceable_lsn,
            "change_count_buckets": len(change_counter_result.change_counter),
            "raw_change_rows": change_counter_result.raw_change_rows,
            "counted_inserts": change_counter_result.counted_inserts,
            "counted_updates": change_counter_result.counted_updates,
            "ignored_inserts": change_counter_result.ignored_inserts,
            "ignored_updates": change_counter_result.ignored_updates,
            "ignored_deletes": change_counter_result.ignored_deletes,
            "applied_upserts": applied_upserts,
            "duration": perf_counter() - start_time,
        }
        current_app.logger.info(
            "%s total replication changes processed",
            change_counter_result.counted_inserts + change_counter_result.counted_updates,
            extra=extra,
        )

        # Return a summary of the replication slot processing results
        return ProcessNotificationsReplicationSlotChangesResult(
            change_count_buckets=len(change_counter_result.change_counter),
            advanced_to_lsn=change_counter_result.advanceable_lsn,
            raw_change_rows=change_counter_result.raw_change_rows,
            counted_inserts=change_counter_result.counted_inserts,
            counted_updates=change_counter_result.counted_updates,
            ignored_inserts=change_counter_result.ignored_inserts,
            ignored_updates=change_counter_result.ignored_updates,
            ignored_deletes=change_counter_result.ignored_deletes,
            applied_upserts=applied_upserts,
        )
    except Exception:
        # Ensure a failed statement does not poison the session for cleanup queries.
        db.session.rollback()
        raise

    finally:
        if lock_acquired:
            _advisory_unlock(advisory_lock_id)


def _try_advisory_lock(lock_id: int) -> bool:
    sql = text("SELECT pg_try_advisory_lock(:lock_id)")
    return bool(db.session.execute(sql, {"lock_id": lock_id}).scalar())


def _advisory_unlock(lock_id: int) -> None:
    db.session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})


def _get_raw_replication_change_rows(
    *,
    slot_name: str,
    upto_nchanges: int,
    table_names: Collection[TableName] = REPLICATION_SLOT_UPDATE_TABLE_NAMES | REPLICATION_SLOT_UPDATE_TABLE_NAMES,
) -> Iterable[tuple[str | None, str | None]]:
    return db.session.execute(
        text(
            """
            SELECT lsn, data
            FROM pg_logical_slot_peek_changes (
                :slot_name,
                NULL,
                :upto_nchanges,
                'include-lsn',
                :include_lsn,
                'format-version',
                :format_version,
                'include-types',
                :include_types,
                'include-typmod',
                :include_typmod,
                'add-tables',
                :table_names
            )
            """
        ),
        {
            "slot_name": slot_name,
            "upto_nchanges": upto_nchanges,
            "include_lsn": "false",
            "format_version": "2",
            "include_types": "false",
            "include_typmod": "false",
            "table_names": ", ".join(str(tn) for tn in table_names),
        },
    ).tuples()


class _BuildChangeCounterResult(NamedTuple):
    change_counter: Counter[FullDimensions]
    advanceable_lsn: str | None
    raw_change_rows: int
    counted_inserts: int
    counted_updates: int
    ignored_inserts: int
    ignored_updates: int
    ignored_deletes: int


# ruff: noqa: C901  # C901 is bunk
def _build_change_counter(
    raw_change_rows: Iterable[tuple[str | None, str | None]],
    *,
    insert_table_names: Container[TableName] = REPLICATION_SLOT_INSERT_TABLE_NAMES,
    update_table_names: Container[TableName] = REPLICATION_SLOT_UPDATE_TABLE_NAMES,
    key_types: Container[str] = REPLICATION_SLOT_KEY_TYPES,
) -> _BuildChangeCounterResult:
    logged_none_payload, logged_none_lsn = False, False
    change_counter: Counter[FullDimensions] = Counter()
    advanceable_lsn: str | None = None
    counted_inserts, counted_updates, ignored_inserts, ignored_updates, ignored_deletes = 0, 0, 0, 0, 0

    i = 0
    # ruff: noqa: B007  # we use `i` after the loop
    for i, (lsn, raw_payload) in enumerate(raw_change_rows, 1):
        if lsn is None and not logged_none_lsn:
            # if we never see this message, can we remove this check?
            current_app.logger.warning("Encountered None replication lsn")
            # avoid potentially spamming the logs
            logged_none_lsn = True

        if raw_payload is None:
            if not logged_none_payload:
                # if we never see this message, can we remove this check?
                current_app.logger.warning("Encountered None replication payload")
                # avoid potentially spamming the logs
                logged_none_payload = True
        else:
            payload = json.loads(raw_payload)

            match payload["action"]:
                case "I":  # insert
                    if TableName(payload["schema"], payload["table"]) in insert_table_names:
                        dimensions = FullDimensions._from_columns(payload["columns"])
                        if dimensions.key_type in key_types:
                            change_counter[dimensions] += 1
                            counted_inserts += 1
                        else:
                            ignored_inserts += 1
                    else:
                        ignored_inserts += 1
                case "U":  # update
                    if TableName(payload["schema"], payload["table"]) in update_table_names:
                        dimensions_new = FullDimensions._from_columns(payload["columns"])
                        dimensions_old = dimensions_new._replace_from_columns(payload["identity"])
                        if dimensions_old.key_type in key_types and dimensions_new != dimensions_old:
                            change_counter[dimensions_old] -= 1
                            change_counter[dimensions_new] += 1
                            counted_updates += 1
                        else:
                            ignored_updates += 1
                    else:
                        ignored_updates += 1
                case "D":  # delete
                    ignored_deletes += 1

            # we only want to advance to LSNs corresponding to commits *or* non-transactional messages. advancing
            # to LSNs inside transactions could lead to trouble. if the final change we encounter isn't one we
            # want to advance to, something is wrong and we'll return a None advanceable_lsn to reflect this.
            if payload["action"] == "C" or (payload["action"] == "M" and not payload["transactional"]):
                advanceable_lsn = lsn
            else:
                advanceable_lsn = None

    return _BuildChangeCounterResult(
        change_counter=change_counter,
        advanceable_lsn=advanceable_lsn,
        raw_change_rows=i,
        counted_inserts=counted_inserts,
        counted_updates=counted_updates,
        ignored_inserts=ignored_inserts,
        ignored_updates=ignored_updates,
        ignored_deletes=ignored_deletes,
    )


def _upsert_notification_status_live_count(counter: Counter[FullDimensions]) -> int:
    count_changes: list[NotificationStatusLiveDimensions] = []

    for dimensions_key, change_count in counter.items():
        if change_count == 0:
            continue

        count_changes.append(
            {
                "bst_date": dimensions_key.bst_date,
                "service_id": dimensions_key.service_id,
                "template_id": dimensions_key.template_id,
                "job_id": dimensions_key.job_id,
                "notification_type": dimensions_key.notification_type,
                "key_type": dimensions_key.key_type,
                "notification_status": dimensions_key.notification_status,
                "notification_count": change_count,
            }
        )

    if count_changes:
        upsert_notification_status_live_counts(count_changes)

    return len(count_changes)


def _advance_replication_slot(lsn: str, *, slot_name: str) -> None:
    db.session.execute(
        text("SELECT pg_replication_slot_advance(:slot_name, :lsn)"),
        {"slot_name": slot_name, "lsn": lsn},
    )
