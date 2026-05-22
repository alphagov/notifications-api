import json
from typing import TypedDict, cast

from sqlalchemy import text

from app import db

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
type RowData = dict[str, JsonValue]


class ReplicationChangeRow(TypedDict):
    lsn: str
    data: str


class OldKeys(TypedDict, total=False):
    keynames: list[str]
    keyvalues: list[JsonValue]


class ReplicationJsonRow(TypedDict, total=False):
    kind: str
    table: str
    columnnames: list[str]
    columnvalues: list[JsonValue]
    oldkeys: OldKeys


class ChangePayload(TypedDict, total=False):
    nextlsn: str
    change: list[ReplicationJsonRow]


class ParsedRow(TypedDict):
    type: str
    table: str
    nextlsn: str | None
    current_row_data: RowData
    previous_row_data: RowData


DEFAULT_CHANGE_ROWS: list[ReplicationJsonRow] = [{}]


def _quote_sql_literal(value: str) -> str:
    """
    Escape single quotes for safe embedding into SQL string literals.

    This helper performs the standard PostgreSQL escaping rule for single
    quotes by doubling them (e.g. `O'Reilly` -> `O''Reilly`). It is used when
    constructing the replication function call via a SQL text string.
    """
    return value.replace("'", "''")


def get_replication_changes(
    *,
    peek: bool = True,
    slot_name: str = "notify_dashboard_replication_slot",
    upto_nchanges: int | None = None,
    table_names: tuple[str, ...] = ("public.notifications",),
    include_lsn: bool | None = None,
    format_version: int | None = None,
    include_types: bool | None = None,
    include_typmod: bool | None = None,
) -> list[ParsedRow]:
    """
    Fetch logical replication changes and normalize them into parsed rows.

    The query calls either:
    - `pg_logical_slot_peek_changes` (non-destructive read), or
    - `pg_logical_slot_get_changes` (consumes changes from the slot)

    Option flags are passed using `wal2json`-compatible key/value arguments.
    Each returned change row is expected to contain a JSON payload in `data`
    and an optional `lsn` fallback.

    Args:
        peek: If True, read changes without advancing the replication slot.
            If False, consume and advance the slot.
        slot_name: Logical replication slot name to read from.
        upto_nchanges: Optional cap for number of changes returned by PostgreSQL.
            `None` maps to SQL `NULL` (database default behavior).
        table_names: Optional tuple of fully-qualified tables to include.
            Passed through `add-tables` option.
        include_lsn: Whether to include LSN in output payload (wal2json option).
        format_version: wal2json format version.
        include_types: Whether to include PostgreSQL type names in output.
        include_typmod: Whether to include typmod metadata in output.

    Returns:
        Flat list of parsed rows produced from all JSON `change` entries.
    """
    options: list[str] = ["pretty-print", "on"]

    if table_names:
        options.extend(["add-tables", ",".join(table_names)])
    if include_lsn is not None:
        options.extend(["include-lsn", "on" if include_lsn else "off"])
    if format_version is not None:
        options.extend(["format-version", str(format_version)])
    if include_types is not None:
        options.extend(["include-types", "on" if include_types else "off"])
    if include_typmod is not None:
        options.extend(["include-typmod", "on" if include_typmod else "off"])

    options_sql = ""
    if options:
        # Build SQL literal list: 'key', 'value', 'key', 'value', ...
        options_sql = ",\n                " + ",\n                ".join(
            f"'{_quote_sql_literal(option)}'" for option in options
        )

    # Choose peek/get behavior based on whether changes should be consumed.
    function_name = "pg_logical_slot_peek_changes" if peek else "pg_logical_slot_get_changes"
    query = f"""
            SELECT * FROM {function_name}(
                '{_quote_sql_literal(slot_name)}',
                NULL,
                {upto_nchanges if upto_nchanges is not None else 'NULL'}{options_sql}
            );
        """

    result = db.session.execute(text(query))
    changes = [dict(change) for change in result.mappings().all()]

    # Flatten per-change payload arrays into one list of normalized rows.
    parsed_data = [row for change in changes for row in (parse_change_data(cast(ReplicationChangeRow, change)) or [])]

    return parsed_data


def parse_change_data(change: ReplicationChangeRow) -> list[ParsedRow] | None:
    """
    Parse a single replication result row into normalized parsed rows.

    The database returns a row containing:
    - `data`: a JSON document produced by wal2json
    - `lsn`: replication position (used as fallback when `nextlsn` is absent)

    If the payload has no `change` entries, `None` is returned so callers can
    skip this item naturally in flattening logic.

    Args:
        change: Raw row from PostgreSQL logical decoding query.

    Returns:
        A list of parsed row dictionaries, or `None` when no change entries
        are present.
    """
    payload = cast(ChangePayload, json.loads(change["data"]))
    nextlsn = payload.get("nextlsn") or change.get("lsn")
    raw_changes = payload.get("change", DEFAULT_CHANGE_ROWS)

    if len(raw_changes) == 0:
        return None

    return [parse_row_data(row, nextlsn=nextlsn) for row in raw_changes]


def parse_row_data(row: ReplicationJsonRow, nextlsn: str | None = None) -> ParsedRow:
    """
    Convert one wal2json change item into the internal `ParsedRow` shape.

    For UPDATE/DELETE events, wal2json may include `oldkeys`, which represent
    key columns from the previous row state. Those are mapped into
    `previous_row_data`.

    Args:
        row: One item from wal2json `change` list.
        nextlsn: Replication position associated with this change item.

    Returns:
        ParsedRow containing event type, table name, LSN, current row values,
        and previous key values.
    """
    column_names = row.get("columnnames", [])
    column_values = row.get("columnvalues", [])

    old_column_names = row.get("oldkeys", {}).get("keynames", [])
    old_column_values = row.get("oldkeys", {}).get("keyvalues", [])

    return {
        "type": row.get("kind", ""),
        "table": row.get("table", ""),
        "nextlsn": nextlsn,
        "current_row_data": dict(zip(column_names, column_values, strict=False)),
        "previous_row_data": dict(zip(old_column_names, old_column_values, strict=False)),
    }


def get_str_value(row_data: RowData, key: str) -> str | None:
    """
    Safely read a string value from a row data mapping.

    Args:
        row_data: Parsed row dictionary containing JSON-compatible values.
        key: Field name to read.

    Returns:
        The string value for `key` when present and of type `str`; otherwise
        `None`.
    """
    value = row_data.get(key)
    if isinstance(value, str):
        return value
    return None


def get_notification_status(row_data: RowData) -> str | None:
    """
    Extract notification status from known status fields.

    This helper supports both legacy/current key names and returns the first
    available string value in this order:
    1. `notification_status`
    2. `status`
    """
    return get_str_value(row_data, "notification_status") or get_str_value(row_data, "status")
