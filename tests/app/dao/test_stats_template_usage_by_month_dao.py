import pytest

from app.dao.stats_template_usage_by_month_dao import insert_or_update_stats_for_template
from app.models import StatsTemplateUsageByMonth

from tests.app.conftest import sample_notification, sample_email_template, sample_template, sample_job, sample_service


def test_create_stats_for_template(notify_db_session, sample_template):
    assert StatsTemplateUsageByMonth.query.count() == 0

    insert_or_update_stats_for_template(sample_template.id, 1, 2017, 10)
    stats_by_month = StatsTemplateUsageByMonth.query.filter(
        StatsTemplateUsageByMonth.template_id == sample_template.id
    ).all()

    assert len(stats_by_month) == 1
    assert stats_by_month[0].template_id == sample_template.id
    assert stats_by_month[0].month == 1
    assert stats_by_month[0].year == 2017
    assert stats_by_month[0].count == 10


def test_update_stats_for_template(notify_db_session, sample_template):
    assert StatsTemplateUsageByMonth.query.count() == 0

    insert_or_update_stats_for_template(sample_template.id, 1, 2017, 10)
    insert_or_update_stats_for_template(sample_template.id, 1, 2017, 20)
    insert_or_update_stats_for_template(sample_template.id, 2, 2017, 30)

    stats_by_month = StatsTemplateUsageByMonth.query.filter(
        StatsTemplateUsageByMonth.template_id == sample_template.id
    ).order_by(StatsTemplateUsageByMonth.template_id).all()

    assert len(stats_by_month) == 2

    assert stats_by_month[0].template_id == sample_template.id
    assert stats_by_month[0].month == 1
    assert stats_by_month[0].year == 2017
    assert stats_by_month[0].count == 20

    assert stats_by_month[1].template_id == sample_template.id
    assert stats_by_month[1].month == 2
    assert stats_by_month[1].year == 2017
    assert stats_by_month[1].count == 30
