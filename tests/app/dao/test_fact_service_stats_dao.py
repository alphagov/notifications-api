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
    mock_query = mocker.patch("app.dao.fact_service_stats_dao.db.session.query")

    apply_service_stats_change(dimensions, -3)

    # check that the correct methods are called on the mock objects
    mock_execute.assert_not_called()
    mock_query.assert_called_once()
    mock_query.assert_called_with(FactServiceStats)

    # check filters passed to the query match the dimensions
    filter_args = mock_query.return_value.filter.call_args.args
    actual_filters = {arg.left.key: arg.right.value for arg in filter_args}
    assert actual_filters == dimensions

    # check that the update was called with the correct values
    mock_query.return_value.filter.return_value.update.assert_called_once()
    update_call = mock_query.return_value.filter.return_value.update.call_args
    assert update_call.kwargs == {"synchronize_session": False}

    # check that the update expression uses the greatest function to ensure the count does not go below zero
    # also checks that the parameters passed to the greatest function include the negative change and zero
    # this is because the update expression is: func.greatest(FactServiceStats.notification_count + change_count, 0)
    update_values = update_call.args[0]
    expression = update_values["notification_count"]
    compiled = expression.compile()

    assert getattr(expression, "name", None) == "greatest"
    assert any(value == -3 for value in compiled.params.values())
    assert any(value == 0 for value in compiled.params.values())
