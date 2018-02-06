from notifications_utils.statsd_decorators import statsd
from sqlalchemy import or_, and_

from app import db
from app.dao.dao_utils import transactional
from app.models import StatsTemplateUsageByMonth, Template


@transactional
@statsd(namespace="dao")
def insert_or_update_stats_for_template(template_id, month, year, count):
    result = db.session.query(
        StatsTemplateUsageByMonth
    ).filter(
        StatsTemplateUsageByMonth.template_id == template_id,
        StatsTemplateUsageByMonth.month == month,
        StatsTemplateUsageByMonth.year == year
    ).update(
        {
            'count': count
        }
    )
    if result == 0:
        monthly_stats = StatsTemplateUsageByMonth(
            template_id=template_id,
            month=month,
            year=year,
            count=count
        )

        db.session.add(monthly_stats)


@statsd(namespace="dao")
def dao_get_template_usage_stats_by_service(service_id, year):
    return db.session.query(
        StatsTemplateUsageByMonth.template_id,
        Template.name,
        Template.template_type,
        StatsTemplateUsageByMonth.month,
        StatsTemplateUsageByMonth.year,
        StatsTemplateUsageByMonth.count
    ).join(
        Template, StatsTemplateUsageByMonth.template_id == Template.id
    ).filter(
        Template.service_id == service_id
    ).filter(
        or_(
            and_(
                StatsTemplateUsageByMonth.month.in_([4, 5, 6, 7, 8, 9, 10, 11, 12]),
                StatsTemplateUsageByMonth.year == year
            ), and_(
                StatsTemplateUsageByMonth.month.in_([1, 2, 3]),
                StatsTemplateUsageByMonth.year == year + 1
            )
        )
    ).all()
