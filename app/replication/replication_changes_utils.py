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
    Process the replication changes and return a list of parsed changes.
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
        options_sql = ",\n                " + ",\n                ".join(
            f"'{_quote_sql_literal(option)}'" for option in options
        )

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

    parsed_data = [row for change in changes for row in (parse_change_data(cast(ReplicationChangeRow, change)) or [])]

    return parsed_data


def parse_change_data(change: ReplicationChangeRow) -> list[ParsedRow] | None:
    """
    Parse the change data and return a dictionary with the relevant information.
    """
    payload = cast(ChangePayload, json.loads(change["data"]))
    nextlsn = payload.get("nextlsn") or change.get("lsn")
    raw_changes = payload.get("change", DEFAULT_CHANGE_ROWS)

    if len(raw_changes) == 0:
        return None

    return [parse_row_data(row, nextlsn=nextlsn) for row in raw_changes]


def parse_row_data(row: ReplicationJsonRow, nextlsn: str | None = None) -> ParsedRow:
    """
    Create a mapping of column names to their values for the given change.
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
    value = row_data.get(key)
    if isinstance(value, str):
        return value
    return None


def get_notification_status(row_data: RowData) -> str | None:
    return get_str_value(row_data, "notification_status") or get_str_value(row_data, "status")
