from datetime import UTC, datetime, timedelta

from app.dao.notifications_dao import dao_get_last_date_template_was_used
from tests.app.db import create_ft_notification_status, create_notification


def test_dao_get_last_date_template_was_used_returns_bst_date_from_stats_table(sample_template):
    last_status_date = (datetime.now(UTC) - timedelta(days=2)).date()
    create_ft_notification_status(bst_date=last_status_date, template=sample_template)

    last_used_date = dao_get_last_date_template_was_used(sample_template)
    assert last_used_date == last_status_date


def test_dao_get_last_date_template_was_used_only_searches_within_one_year(sample_template):
    last_status_date = (datetime.now(UTC) - timedelta(days=400)).date()
    create_ft_notification_status(bst_date=last_status_date, template=sample_template)

    last_used_date = dao_get_last_date_template_was_used(sample_template)
    assert last_used_date is None


def test_dao_get_last_date_template_was_used_returns_created_at_from_notifications(sample_template):
    last_notification_date = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
    create_notification(template=sample_template, created_at=last_notification_date)

    last_status_date = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)).date()
    create_ft_notification_status(bst_date=last_status_date, template=sample_template)
    last_used_date = dao_get_last_date_template_was_used(sample_template)
    assert last_used_date == last_notification_date


def test_dao_get_last_date_template_was_used_returns_none_if_never_used(sample_template):
    assert not dao_get_last_date_template_was_used(sample_template)
