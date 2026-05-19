import json
from typing import TypedDict, cast

from sqlalchemy import text

from app import db

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
type RowData = dict[str, JsonValue]


class ReplicationChangeRow(TypedDict):
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
    change: list[ReplicationJsonRow]


class ParsedRow(TypedDict):
    type: str
    table: str
    current_row_data: RowData
    previous_row_data: RowData


DEFAULT_CHANGE_ROWS: list[ReplicationJsonRow] = [{}]


def get_replication_changes(peek: bool = True) -> list[ParsedRow]:
    """
    Process the replication changes and return a list of parsed changes.
    """
    result = db.session.execute(
        text(f"""
            SELECT * FROM {"pg_logical_slot_peek_changes" if peek else "pg_logical_slot_get_changes"}(
                'notify_dashboard_replication_slot',
                NULL,
                NULL,
                'pretty-print', 'on',
                'add-tables', 'public.notifications'
            );
        """)
    )
    changes = [dict(change) for change in result.mappings().all()]

    parsed_data = [row for change in changes for row in (parse_change_data(cast(ReplicationChangeRow, change)) or [])]

    return parsed_data


def parse_change_data(change: ReplicationChangeRow) -> list[ParsedRow] | None:
    """
    Parse the change data and return a dictionary with the relevant information.
    """
    payload = cast(ChangePayload, json.loads(change["data"]))
    raw_changes = payload.get("change", DEFAULT_CHANGE_ROWS)

    if len(raw_changes) == 0:
        return None

    return [parse_row_data(row) for row in raw_changes]


def parse_row_data(row: ReplicationJsonRow) -> ParsedRow:
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
        "current_row_data": dict(zip(column_names, column_values, strict=False)),
        "previous_row_data": dict(zip(old_column_names, old_column_values, strict=False)),
    }
