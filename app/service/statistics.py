import itertools
from datetime import datetime, timedelta

from app.models import NOTIFICATION_STATUS_TYPES, TEMPLATE_TYPES


def format_statistics(statistics):
    # statistics come in a named tuple with uniqueness from 'notification_type', 'status' - however missing
    # statuses/notification types won't be represented and the status types need to be simplified/summed up
    # so we can return emails/sms * created, sent, and failed
    counts = create_zeroed_stats_dicts()
    for row in statistics:
        _update_statuses_from_row(counts[row.notification_type], row)

    return counts


def format_monthly_template_notification_stats(year, rows):
    stats = {
        datetime.strftime(date, '%Y-%m'): {}
        for date in [
            datetime(year, month, 1) for month in range(4, 13)
        ] + [
            datetime(year + 1, month, 1) for month in range(1, 4)
        ]
    }

    for row in rows:
        formatted_month = row.month.strftime('%Y-%m')
        if str(row.template_id) not in stats[formatted_month]:
            stats[formatted_month][str(row.template_id)] = {
                "name": row.name,
                "type": row.template_type,
                "counts": dict.fromkeys(NOTIFICATION_STATUS_TYPES, 0)
            }
        stats[formatted_month][str(row.template_id)]["counts"][row.status] += row.count

    return stats


def create_zeroed_stats_dicts():
    return {
        template_type: {
            status: 0 for status in ('requested', 'delivered', 'failed')
        } for template_type in TEMPLATE_TYPES
    }


def _update_statuses_from_row(update_dict, row):
    update_dict['requested'] += row.count
    if row.status in ('delivered', 'sent'):
        update_dict['delivered'] += row.count
    elif row.status in ('failed', 'technical-failure', 'temporary-failure', 'permanent-failure'):
        update_dict['failed'] += row.count
