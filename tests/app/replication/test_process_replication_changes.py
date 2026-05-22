import json
from unittest.mock import MagicMock, patch

from app.replication.replication_changes_utils import (
    get_notification_status,
    get_replication_changes,
    get_str_value,
    parse_change_data,
    parse_row_data,
)


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

    mock_result = MagicMock()
    mock_result.mappings().all.return_value = [first_change, second_change]

    with patch("app.replication.replication_changes_utils.db.session.execute", return_value=mock_result):
        result = get_replication_changes()

    assert result == [
        {
            "type": "insert",
            "table": "notifications",
            "nextlsn": None,
            "current_row_data": {"id": "111", "to": "447700900001"},
            "previous_row_data": {},
        },
        {
            "type": "update",
            "table": "notifications",
            "nextlsn": None,
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
        "nextlsn": None,
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


def test_parse_change_data_propagates_nextlsn_to_all_rows():
    result = parse_change_data(
        {
            "data": json.dumps(
                {
                    "nextlsn": "0/16B6A28",
                    "change": [
                        {
                            "kind": "insert",
                            "table": "notifications",
                            "columnnames": ["id", "status"],
                            "columnvalues": ["abc", "sending"],
                        }
                    ],
                }
            ),
            "lsn": "0/16B6A20",
        }
    )

    assert result == [
        {
            "type": "insert",
            "table": "notifications",
            "nextlsn": "0/16B6A28",
            "current_row_data": {"id": "abc", "status": "sending"},
            "previous_row_data": {},
        }
    ]


def test_get_str_value_returns_none_for_non_string_values():
    assert get_str_value({"status": 123}, "status") is None


def test_get_notification_status_prefers_notification_status_key():
    result = get_notification_status({"notification_status": "delivered", "status": "sending"})

    assert result == "delivered"


def test_get_notification_status_falls_back_to_status_key():
    result = get_notification_status({"status": "temporary-failure"})

    assert result == "temporary-failure"
