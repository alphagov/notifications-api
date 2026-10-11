from datetime import date
from uuid import uuid4

from sqlalchemy.dialects.postgresql.dml import Insert

from app.dao.fact_service_stats_dao import apply_service_stats_change
from app.models import FactServiceStats


def test_apply_service_stats_change_for_non_zero_change(mocker):
    dimensions = {
        "bst_date": date(2026, 8, 6),
        "service_id": uuid4(),
        "template_id": uuid4(),
        "notification_type": "sms",
        "notification_status": "delivered",
    }
    mock_execute = mocker.patch("app.dao.fact_service_stats_dao.db.session.execute")

    apply_service_stats_change(dimensions, 4)

    mock_execute.assert_called_once()
    statement = mock_execute.call_args.args[0]
    params = statement.compile().params

    assert isinstance(statement, Insert)
    assert statement.table == FactServiceStats.__table__
    assert params["bst_date"] == dimensions["bst_date"]
    assert params["service_id"] == dimensions["service_id"]
    assert params["template_id"] == dimensions["template_id"]
    assert params["notification_type"] == dimensions["notification_type"]
    assert params["notification_status"] == dimensions["notification_status"]
    assert params["notification_count"] == 4

    # This is needed because the on_conflict_do_update() method generates
    # a parameter name like "notification_count_1" for the update clause,
    # so we need to check that one of the parameters starts with "notification_count_" and has the value 4.
    assert any(key.startswith("notification_count_") and value == 4 for key, value in params.items())


def test_apply_service_stats_change_for_zero_change(mocker):
    dimensions = {
        "bst_date": date(2026, 8, 6),
        "service_id": uuid4(),
        "template_id": uuid4(),
        "notification_type": "sms",
        "notification_status": "delivered",
    }
    mock_execute = mocker.patch("app.dao.fact_service_stats_dao.db.session.execute")
    mock_query = mocker.patch("app.dao.fact_service_stats_dao.db.session.query")

    apply_service_stats_change(dimensions, 0)

    mock_execute.assert_not_called()
    mock_query.assert_not_called()


def test_apply_service_stats_change_for_negative_change(mocker):
    dimensions = {
        "bst_date": date(2026, 8, 6),
        "service_id": uuid4(),
        "template_id": uuid4(),
        "notification_type": "sms",
        "notification_status": "delivered",
    }
    mock_execute = mocker.patch("app.dao.fact_service_stats_dao.db.session.execute")
    mock_commit = mocker.patch("app.dao.fact_service_stats_dao.db.session.commit")

    apply_service_stats_change(dimensions, -3)

    mock_execute.assert_called_once()
    mock_commit.assert_called_once()

    statement = mock_execute.call_args.args[0]
    params = statement.compile().params

    assert isinstance(statement, Insert)
    assert statement.table == FactServiceStats.__table__
    assert params["bst_date"] == dimensions["bst_date"]
    assert params["service_id"] == dimensions["service_id"]
    assert params["template_id"] == dimensions["template_id"]
    assert params["notification_type"] == dimensions["notification_type"]
    assert params["notification_status"] == dimensions["notification_status"]
    assert params["notification_count"] == -3
    assert any(key.startswith("notification_count_") and value == -3 for key, value in params.items())
