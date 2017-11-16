from app import db
from app.dao.stats_template_usage_by_month_dao import (
    insert_or_update_stats_for_template,
    dao_get_template_usage_stats_by_service
)
from app.models import StatsTemplateUsageByMonth

from tests.app.db import create_service, create_template


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


def test_dao_get_template_usage_stats_by_service(sample_service):

    email_template = create_template(service=sample_service, template_type="email")

    stats1 = StatsTemplateUsageByMonth(
        template_id=email_template.id,
        month=1,
        year=2017,
        count=10
    )

    stats2 = StatsTemplateUsageByMonth(
        template_id=email_template.id,
        month=2,
        year=2017,
        count=10
    )

    db.session.add(stats1)
    db.session.add(stats2)

    result = dao_get_template_usage_stats_by_service(sample_service.id, 2017)

    assert len(result) == 2


def test_dao_get_template_usage_stats_by_service_specific_year(sample_service):

    email_template = create_template(service=sample_service, template_type="email")

    stats1 = StatsTemplateUsageByMonth(
        template_id=email_template.id,
        month=1,
        year=2016,
        count=10
    )

    stats2 = StatsTemplateUsageByMonth(
        template_id=email_template.id,
        month=2,
        year=2017,
        count=10
    )

    db.session.add(stats1)
    db.session.add(stats2)

    result = dao_get_template_usage_stats_by_service(sample_service.id, 2017)

    assert len(result) == 1
    assert result[0].template_id == email_template.id
    assert result[0].name == email_template.name
    assert result[0].template_type == email_template.template_type
    assert result[0].month == 2
    assert result[0].year == 2017
    assert result[0].count == 10
