import json

from app.replication.process_replication_changes import parse_change_data, parse_row_data, process_replication_changes


def test_process_replication_changes_flattens_rows_across_changes():
    first_change = {
        "data": json.dumps(
            {
                "change": [
                    {
                        "kind": "insert",
                        "table": "notifications",
                        "columnnames": ["id", "to"],
                        "columnvalues": ["111", "447700900001"],
                    }
                ]
            }
        )
    }
    second_change = {
        "data": json.dumps(
            {
                "change": [
                    {
                        "kind": "update",
                        "table": "notifications",
                        "columnnames": ["id", "status"],
                        "columnvalues": ["222", "sent"],
                    }
                ]
            }
        )
    }

    result = process_replication_changes([first_change, second_change])

    assert result == [
        {
            "type": "insert",
            "table": "notifications",
            "current_row_data": {"id": "111", "to": "447700900001"},
            "previous_row_data": {},
        },
        {
            "type": "update",
            "table": "notifications",
            "current_row_data": {"id": "222", "status": "sent"},
            "previous_row_data": {},
        },
    ]


def test_parse_change_data_returns_none_for_empty_change_list():
    result = parse_change_data({"data": json.dumps({"change": []})})

    assert result is None


def test_parse_row_data_maps_current_and_previous_rows():
    row = {
        "kind": "update",
        "table": "notifications",
        "columnnames": ["id", "status", "to"],
        "columnvalues": ["abc", "delivered", "447700900002"],
        "oldkeys": {
            "keynames": ["id", "status"],
            "keyvalues": ["abc", "sending"],
        },
    }

    result = parse_row_data(row)

    assert result == {
        "type": "update",
        "table": "notifications",
        "current_row_data": {
            "id": "abc",
            "status": "delivered",
            "to": "447700900002",
        },
        "previous_row_data": {
            "id": "abc",
            "status": "sending",
        },
    }
