from datetime import datetime, timedelta
from app.dao.notifications_dao import dao_get_last_date_template_was_used
from tests.app.db import create_notification, create_ft_notification_status


def test_dao_get_last_date_template_was_used_returns_bst_date_from_stats_table(
        sample_template
):
    last_status_date = (datetime.utcnow() - timedelta(days=2)).date()
    create_ft_notification_status(bst_date=last_status_date,
                                  template=sample_template)

    last_used_date = dao_get_last_date_template_was_used(template_id=sample_template.id,
                                                         service_id=sample_template.service_id)
    assert last_used_date == last_status_date


def test_dao_get_last_date_template_was_used_returns_created_at_from_notifications(
        sample_template
):
    last_notification_date = datetime.utcnow() - timedelta(hours=2)
    create_notification(template=sample_template, created_at=last_notification_date)

    last_status_date = (datetime.utcnow() - timedelta(days=2)).date()
    create_ft_notification_status(bst_date=last_status_date, template=sample_template)
    last_used_date = dao_get_last_date_template_was_used(template_id=sample_template.id,
                                                         service_id=sample_template.service_id)
    assert last_used_date == last_notification_date


def test_dao_get_last_date_template_was_used_returns_none_if_never_used(sample_template):
    assert not dao_get_last_date_template_was_used(template_id=sample_template.id,
                                                   service_id=sample_template.service_id)
