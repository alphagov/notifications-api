from unittest.mock import Mock

import pytest
from celery.exceptions import Retry

from app.celery.process_replication_slot_changes import check_replication_slot_changes


def test_check_replication_slot_changes_logs_change_count(mocker, caplog):
    mock_result = Mock()
    mock_result.fetchall.return_value = [{"lsn": "one"}, {"lsn": "two"}]
    mock_execute = mocker.patch(
        "app.celery.process_replication_slot_changes.db.session.execute", return_value=mock_result
    )

    with caplog.at_level("INFO"):
        check_replication_slot_changes()

    assert mock_execute.call_count == 1

    query = mock_execute.call_args.args[0]
    assert "pg_logical_slot_peek_changes" in str(query)

    assert "Replication slot changes retrieved" in caplog.messages
    record = next(record for record in caplog.records if record.msg == "Replication slot changes retrieved")
    assert record.changes_count == 2


def test_check_replication_slot_changes_calls_retry_on_query_error(mocker):
    mocker.patch("app.celery.process_replication_slot_changes.db.session.execute", side_effect=Exception("EXPECTED"))
    mock_retry = mocker.patch.object(check_replication_slot_changes, "retry", side_effect=Retry("retry"))

    with pytest.raises(Retry):
        check_replication_slot_changes()

    assert mock_retry.call_count == 1
    _, kwargs = mock_retry.call_args
    assert kwargs["countdown"] == 1
