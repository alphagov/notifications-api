from datetime import date, datetime
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql.dml import Insert

from app.dao.fact_notification_status_live_dao import apply_notification_status_live_change
from app.models import FactNotificationStatusLive


def test_apply_notification_status_live_change_for_non_zero_change(mocker):
    dimensions = {
        "bst_date": date(2026, 8, 6),
        "service_id": uuid4(),
        "template_id": uuid4(),
        "job_id": uuid4(),
        "key_type": "normal",
        "notification_type": "sms",
        "notification_status": "delivered",
    }
    mock_execute = mocker.patch("app.dao.fact_notification_status_live_dao.db.session.execute")

    apply_notification_status_live_change(dimensions, 4)

    mock_execute.assert_called_once()
    statement = mock_execute.call_args.args[0]
    params = statement.compile().params
    compiled_statement = statement.compile(dialect=postgresql.dialect())

    assert isinstance(statement, Insert)
    assert statement.table == FactNotificationStatusLive.__table__
    assert params["bst_date"] == dimensions["bst_date"]
    assert params["service_id"] == dimensions["service_id"]
    assert params["template_id"] == dimensions["template_id"]
    assert params["job_id"] == dimensions["job_id"]
    assert params["key_type"] == dimensions["key_type"]
    assert params["notification_type"] == dimensions["notification_type"]
    assert params["notification_status"] == dimensions["notification_status"]
    assert params["notification_count"] == 4
    assert "updated_at =" in compiled_statement.string
    assert isinstance(compiled_statement.params["param_1"], datetime)

    assert any(key.startswith("notification_count_") and value == 4 for key, value in params.items())


def test_apply_notification_status_live_change_for_zero_change(mocker):
    dimensions = {
        "bst_date": date(2026, 8, 6),
        "service_id": uuid4(),
        "template_id": uuid4(),
        "job_id": uuid4(),
        "key_type": "normal",
        "notification_type": "sms",
        "notification_status": "delivered",
    }
    mock_execute = mocker.patch("app.dao.fact_notification_status_live_dao.db.session.execute")
    mock_commit = mocker.patch("app.dao.fact_notification_status_live_dao.db.session.commit")

    apply_notification_status_live_change(dimensions, 0)

    mock_execute.assert_not_called()
    mock_commit.assert_not_called()


def test_apply_notification_status_live_change_for_negative_change(mocker):
    dimensions = {
        "bst_date": date(2026, 8, 6),
        "service_id": uuid4(),
        "template_id": uuid4(),
        "job_id": uuid4(),
        "key_type": "normal",
        "notification_type": "sms",
        "notification_status": "delivered",
    }
    mock_execute = mocker.patch("app.dao.fact_notification_status_live_dao.db.session.execute")
    mock_commit = mocker.patch("app.dao.fact_notification_status_live_dao.db.session.commit")

    apply_notification_status_live_change(dimensions, -3)

    mock_execute.assert_called_once()
    mock_commit.assert_called_once()

    statement = mock_execute.call_args.args[0]
    params = statement.compile().params

    assert isinstance(statement, Insert)
    assert statement.table == FactNotificationStatusLive.__table__
    assert params["bst_date"] == dimensions["bst_date"]
    assert params["service_id"] == dimensions["service_id"]
    assert params["template_id"] == dimensions["template_id"]
    assert params["job_id"] == dimensions["job_id"]
    assert params["key_type"] == dimensions["key_type"]
    assert params["notification_type"] == dimensions["notification_type"]
    assert params["notification_status"] == dimensions["notification_status"]
    assert params["notification_count"] == -3
    assert any(key.startswith("notification_count_") and value == -3 for key, value in params.items())
