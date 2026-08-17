from collections import Counter
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.dao import notifications_wal_changes_dao as dao


def _build_change(
    *,
    table: str = "notifications",
    change_type: str = "insert",
    current_row_data: dict | None = None,
    previous_row_data: dict | None = None,
    nextlsn: str | None = None,
) -> dict:
    return {
        "table": table,
        "type": change_type,
        "current_row_data": current_row_data or {},
        "previous_row_data": previous_row_data or {},
        "nextlsn": nextlsn,
    }


def test_zip_values():
    assert dao._zip_values(["a", None, "c"], [1, 2, 3]) == {"a": 1, "c": 3}


def test_extract_row_data_from_columnnames_and_columnvalues():
    change = {"columnnames": ["service_id", "notification_type"], "columnvalues": ["abc", "sms"]}

    assert dao._extract_row_data(change) == {"service_id": "abc", "notification_type": "sms"}


def test_extract_row_data_from_columns():
    change = {
        "columns": [
            {"name": "service_id", "value": "abc"},
            {"name": "notification_type", "value": "email"},
            {"name": None, "value": "ignored"},
        ]
    }

    assert dao._extract_row_data(change) == {"service_id": "abc", "notification_type": "email"}


def test_extract_row_data_returns_empty_when_not_present():
    assert dao._extract_row_data({}) == {}


def test_extract_previous_row_data_from_keynames_and_keyvalues():
    change = {"oldkeys": {"keynames": ["notification_status"], "keyvalues": ["created"]}}

    assert dao._extract_previous_row_data(change) == {"notification_status": "created"}


def test_extract_previous_row_data_from_keys():
    change = {
        "oldkeys": {
            "keys": [
                {"name": "notification_status", "value": "sending"},
                {"name": None, "value": "ignored"},
            ]
        }
    }

    assert dao._extract_previous_row_data(change) == {"notification_status": "sending"}


def test_extract_previous_row_data_returns_empty_when_not_present():
    assert dao._extract_previous_row_data({}) == {}


def test_parse_wal2json_payload_filters_table_and_maps_fields(mocker):
    mock_row = mocker.patch("app.dao.notifications_wal_changes_dao._extract_row_data", return_value={"a": 1})
    mock_previous = mocker.patch(
        "app.dao.notifications_wal_changes_dao._extract_previous_row_data", return_value={"b": 2}
    )
    payload = {
        "nextlsn": "0/AA",
        "change": [
            {"schema": "public", "table": "notifications", "kind": "insert"},
            {"schema": "public", "table": "other", "kind": "insert"},
            {"table": "notifications", "type": "update", "nextlsn": "0/BB"},
            {"schema": "public"},
        ],
    }

    result = dao._parse_wal2json_payload(payload, table_name="public.notifications")

    assert result == [
        {
            "table": "notifications",
            "type": "insert",
            "current_row_data": {"a": 1},
            "previous_row_data": {"b": 2},
            "nextlsn": "0/AA",
        }
    ]
    assert mock_row.call_count == 1
    assert mock_previous.call_count == 1


def test_get_replication_changes_parses_rows_and_payload_formats(mocker):
    mappings_rows = [
        {"data": '{"change": [{"schema": "public", "table": "notifications", "kind": "insert"}]}'},
        {"data": {"change": [{"schema": "public", "table": "notifications", "kind": "update"}]}},
        {"data": None},
    ]

    execute_result = mocker.Mock()
    execute_result.mappings.return_value = mappings_rows
    mock_execute = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute", return_value=execute_result)
    mock_parser = mocker.patch(
        "app.dao.notifications_wal_changes_dao._parse_wal2json_payload",
        side_effect=[[{"table": "notifications", "type": "insert"}], [{"table": "notifications", "type": "update"}]],
    )

    result = dao._get_replication_changes(slot_name="slot", upto_nchanges=20, table_name="public.notifications")

    assert result == [{"table": "notifications", "type": "insert"}, {"table": "notifications", "type": "update"}]
    assert mock_execute.call_count == 1
    assert mock_parser.call_count == 2


def test_get_replication_changes_keeps_sql_lsn(mocker):
    mappings_rows = [{"lsn": "0/AB", "data": {"change": [{"schema": "public", "table": "notifications", "kind": "insert"}]}}]

    execute_result = mocker.Mock()
    execute_result.mappings.return_value = mappings_rows
    mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute", return_value=execute_result)

    result = dao._get_replication_changes(slot_name="slot", upto_nchanges=20, table_name="public.notifications")

    assert result[0]["lsn"] == "0/AB"


def test_parse_wal2json_payload_supports_format_2_rows():
    payload = {
        "action": "I",
        "schema": "public",
        "table": "notifications",
        "columns": [
            {"name": "service_id", "value": "550e8400-e29b-41d4-a716-446655440000"},
            {"name": "template_id", "value": "550e8400-e29b-41d4-a716-446655440001"},
            {"name": "notification_type", "value": "sms"},
            {"name": "key_type", "value": "normal"},
            {"name": "notification_status", "value": "created"},
            {"name": "created_at", "value": "2026-08-12T10:00:00Z"},
        ],
    }

    result = dao._parse_wal2json_payload(payload, table_name="public.notifications")

    assert len(result) == 1
    assert result[0]["table"] == "notifications"
    assert result[0]["type"] == "insert"
    assert result[0]["current_row_data"]["notification_type"] == "sms"
    assert result[0]["current_row_data"]["notification_status"] == "created"


def test_get_replication_changes_uses_format_version_2(mocker):
    execute_result = mocker.Mock()
    execute_result.mappings.return_value = [{"data": {"change": []}}]
    mock_execute = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute", return_value=execute_result)
    mocker.patch("app.dao.notifications_wal_changes_dao._parse_wal2json_payload", return_value=[])

    dao._get_replication_changes(slot_name="slot", upto_nchanges=20, table_name="public.notifications")

    assert mock_execute.call_count == 1
    assert mock_execute.call_args.args[1]["format_version"] == "2"


def test_parse_uuid_value():
    value = str(uuid4())
    assert dao._parse_uuid_value({"service_id": value}, "service_id") == UUID(value)
    assert dao._parse_uuid_value({"service_id": "not-a-uuid"}, "service_id") is None
    assert dao._parse_uuid_value({}, "service_id") is None


def test_get_str_value():
    assert dao._get_str_value({"a": "x"}, "a") == "x"
    assert dao._get_str_value({"a": 42}, "a") == "42"
    assert dao._get_str_value({"a": None}, "a") is None
    assert dao._get_str_value(None, "a") is None


def test_parse_datetime_value():
    assert dao._parse_datetime_value({"created_at": "2026-08-06T10:00:00Z"}, "created_at") == datetime(
        2026, 8, 6, 10, 0, 0, tzinfo=UTC
    )
    assert dao._parse_datetime_value({"created_at": "invalid"}, "created_at") is None
    assert dao._parse_datetime_value({}, "created_at") is None


def test_build_dimensions_returns_tuple(mocker):
    service_id = str(uuid4())
    template_id = str(uuid4())
    created_at = datetime(2026, 8, 6, 10, 0, 0, tzinfo=UTC)
    mock_convert = mocker.patch("app.dao.notifications_wal_changes_dao.convert_utc_to_bst", return_value=created_at)
    change = _build_change(
        current_row_data={
            "service_id": service_id,
            "template_id": template_id,
            "notification_type": "sms",
            "key_type": "normal",
            "notification_status": "delivered",
            "created_at": "2026-08-06T10:00:00Z",
        }
    )

    result = dao._build_dimensions(change, use_previous_row=False)

    assert result == (date(2026, 8, 6), UUID(template_id), UUID(service_id), "sms", "delivered")
    mock_convert.assert_called_once_with(created_at)


def test_build_dimensions_uses_fallback_row_when_primary_missing(mocker):
    service_id = str(uuid4())
    template_id = str(uuid4())
    mocker.patch(
        "app.dao.notifications_wal_changes_dao.convert_utc_to_bst",
        return_value=datetime(2026, 8, 7, 0, 0, tzinfo=UTC),
    )
    change = _build_change(
        current_row_data={},
        previous_row_data={
            "service_id": service_id,
            "template_id": template_id,
            "notification_type": "email",
            "key_type": "normal",
            "notification_status": "failed",
            "created_at": "2026-08-07T00:00:00Z",
        },
    )

    result = dao._build_dimensions(change, use_previous_row=False)

    assert result == (date(2026, 8, 7), UUID(template_id), UUID(service_id), "email", "failed")


def test_build_dimensions_returns_none_for_test_key_type():
    change = _build_change(current_row_data={"key_type": "test"})

    assert dao._build_dimensions(change, use_previous_row=False) is None


def test_build_dimensions_returns_none_when_required_fields_missing():
    change = _build_change(current_row_data={"key_type": "normal"})

    assert dao._build_dimensions(change, use_previous_row=False) is None


def test_build_counter_from_changes():
    service_id = str(uuid4())
    template_id = str(uuid4())
    base = {
        "service_id": service_id,
        "template_id": template_id,
        "notification_type": "sms",
        "key_type": "normal",
        "created_at": "2026-08-06T10:00:00Z",
    }

    changes = [
        _build_change(
            change_type="insert", current_row_data={**base, "notification_status": "created"}, nextlsn="0/01"
        ),
        _build_change(
            change_type="update",
            current_row_data={**base, "notification_status": "delivered"},
            previous_row_data={**base, "notification_status": "created"},
            nextlsn="0/02",
        ),
        _build_change(table="other", change_type="insert", current_row_data={**base, "notification_status": "created"}),
        _build_change(
            change_type="delete", current_row_data={**base, "notification_status": "created"}, nextlsn="0/03"
        ),
    ]

    counter, processed_changes, ignored_changes, last_nextlsn = dao._build_counter_from_changes(changes)

    created_key = dao._build_dimensions(changes[0], use_previous_row=False)
    delivered_key = dao._build_dimensions(changes[1], use_previous_row=False)

    assert counter[created_key] == 0
    assert counter[delivered_key] == 1
    assert processed_changes == 2
    assert ignored_changes == 2
    assert last_nextlsn == "0/03"


def test_aggregate_service_stats_change_counts_reorders_dimensions():
    service_id = uuid4()
    template_id = uuid4()
    full_dimensions = (date(2026, 8, 6), template_id, service_id, "sms", "delivered")

    result = dao._aggregate_service_stats_change_counts(Counter({full_dimensions: 4}))

    assert result[(date(2026, 8, 6), service_id, template_id, "sms", "delivered")] == 4


def test_try_advisory_lock(mocker):
    execute_result = mocker.Mock()
    execute_result.scalar.return_value = True
    mock_execute = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute", return_value=execute_result)

    result = dao._try_advisory_lock(123)

    assert result is True
    assert mock_execute.call_count == 1


def test_advisory_unlock(mocker):
    mock_execute = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute")

    dao._advisory_unlock(123)

    mock_execute.assert_called_once()


def test_advance_replication_slot(mocker):
    mock_execute = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute")

    dao._advance_replication_slot("0/AA", slot_name="slot")

    mock_execute.assert_called_once()


def test_dao_process_notifications_replication_slot_changes_when_lock_not_acquired(mocker):
    mock_try_lock = mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=False)
    mock_get_changes = mocker.patch("app.dao.notifications_wal_changes_dao._get_replication_changes")
    mock_unlock = mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")

    result = dao.dao_process_notifications_replication_slot_changes(
        slot_name="slot", upto_nchanges=200, advisory_lock_id=9
    )

    assert result == {"lock_acquired": False, "slot_name": "slot", "upto_nchanges": 200}
    mock_try_lock.assert_called_once_with(9)
    mock_get_changes.assert_not_called()
    mock_unlock.assert_not_called()


def test_dao_process_notifications_replication_slot_changes_when_no_changes(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._get_replication_changes", return_value=[])
    mock_commit = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.commit")
    mock_unlock = mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")

    result = dao.dao_process_notifications_replication_slot_changes(advisory_lock_id=11)

    assert result == {
        "lock_acquired": True,
        "changes_count": 0,
        "processed_changes": 0,
        "ignored_changes": 0,
        "service_stats_change_count_buckets": 0,
        "last_nextlsn": None,
    }
    mock_commit.assert_not_called()
    mock_unlock.assert_called_once_with(11)


def test_dao_process_notifications_replication_slot_changes_success(mocker):
    dimensions_key = (date(2026, 8, 6), uuid4(), uuid4(), "sms", "delivered")
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._get_replication_changes", return_value=[{"x": 1}, {"x": 2}])
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._build_counter_from_changes",
        return_value=(Counter(), 2, 0, "0/AB"),
    )
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._aggregate_service_stats_change_counts",
        return_value=Counter({dimensions_key: 3, (date(2026, 8, 6), uuid4(), uuid4(), "email", "failed"): 0}),
    )
    mock_apply = mocker.patch("app.dao.notifications_wal_changes_dao.apply_service_stats_change")
    mock_commit = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.commit")
    mock_advance = mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")
    mock_unlock = mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")

    result = dao.dao_process_notifications_replication_slot_changes(slot_name="slot")

    assert result == {
        "lock_acquired": True,
        "changes_count": 2,
        "processed_changes": 2,
        "ignored_changes": 0,
        "service_stats_change_count_buckets": 2,
        "last_nextlsn": "0/AB",
    }
    mock_apply.assert_called_once()
    apply_args = mock_apply.call_args.args
    assert apply_args[1] == 3
    assert apply_args[0] == {
        "bst_date": dimensions_key[0],
        "service_id": dimensions_key[1],
        "template_id": dimensions_key[2],
        "notification_type": dimensions_key[3],
        "notification_status": dimensions_key[4],
    }
    mock_commit.assert_called_once()
    mock_advance.assert_called_once_with("0/AB", slot_name="slot")
    mock_unlock.assert_called_once()


def test_dao_process_notifications_replication_slot_changes_rollback_and_reraises(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._get_replication_changes", side_effect=RuntimeError("boom"))
    mock_rollback = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")
    mock_logger = mocker.patch("app.dao.notifications_wal_changes_dao.current_app.logger.exception")
    mock_unlock = mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")

    with pytest.raises(RuntimeError, match="boom"):
        dao.dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    mock_rollback.assert_called_once()
    mock_logger.assert_called_once_with("[FAILED] Replication slot changes")
    mock_unlock.assert_called_once_with(77)


def test_dao_process_notifications_replication_slot_changes_logs_unlock_failure(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._get_replication_changes", return_value=[])
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock", side_effect=RuntimeError("unlock failed"))
    mock_logger = mocker.patch("app.dao.notifications_wal_changes_dao.current_app.logger.exception")

    dao.dao_process_notifications_replication_slot_changes(advisory_lock_id=88)

    assert mock_logger.call_count == 1
    logger_args = mock_logger.call_args
    assert logger_args.args[0] == "Failed to release advisory lock"
    assert logger_args.kwargs == {"extra": {"dao_method": "dao_process_replication_slot_changes"}}
