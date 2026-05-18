import json

from sqlalchemy import text

from app import db


def get_replication_changes(peak=True):
    """
    Process the replication changes and return a list of parsed changes.
    """
    result = db.session.execute(
        text(f"""
            SELECT * FROM {"pg_logical_slot_peek_changes" if peak else "pg_logical_slot_get_changes"}(
                'notify_dashboard_replication_slot',
                NULL,
                NULL,
                'pretty-print', 'on',
                'add-tables', 'public.notifications'
            );
        """)
    )
    changes = [dict(change) for change in result.mappings().all()]

    parsed_data = [row for change in changes for row in (parse_change_data(change) or [])]

    return parsed_data


def parse_change_data(change):
    """
    Parse the change data and return a dictionary with the relevant information.
    """
    change = json.loads(change["data"]).get("change", [{}])

    if len(change) == 0:
        return None

    return list(map(parse_row_data, change))


def parse_row_data(row):
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
