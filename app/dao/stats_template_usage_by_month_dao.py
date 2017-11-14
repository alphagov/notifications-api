from app import db
from app.models import StatsTemplateUsageByMonth


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
