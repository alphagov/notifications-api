import itertools
from datetime import datetime, timedelta

from app.models import TEMPLATE_TYPES


def format_statistics(statistics):
    # statistics come in a named tuple with uniqueness from 'notification_type', 'status' - however missing
    # statuses/notification types won't be represented and the status types need to be simplified/summed up
    # so we can return emails/sms * created, sent, and failed
    counts = create_zeroed_stats_dicts()
    for row in statistics:
        _update_statuses_from_row(counts[row.notification_type], row)

    return counts


def format_weekly_notification_stats(statistics, service_created_at):
    preceeding_monday = (service_created_at - timedelta(days=service_created_at.weekday()))
    # turn a datetime into midnight that day http://stackoverflow.com/a/1937636
    preceeding_monday_midnight = datetime.combine(preceeding_monday.date(), datetime.min.time())
    week_dict = {
        week: create_zeroed_stats_dicts()
        for week in _weeks_for_range(preceeding_monday_midnight, datetime.utcnow())
    }
    for row in statistics:
        _update_statuses_from_row(week_dict[row.week_start][row.notification_type], row)

    return week_dict


def create_zeroed_stats_dicts():
    return {
        template_type: {
            status: 0 for status in ('requested', 'delivered', 'failed')
        } for template_type in TEMPLATE_TYPES
    }


def _update_statuses_from_row(update_dict, row):
    update_dict['requested'] += row.count
    if row.status == 'delivered':
        update_dict['delivered'] += row.count
    elif row.status in ('failed', 'technical-failure', 'temporary-failure', 'permanent-failure'):
        update_dict['failed'] += row.count


def _weeks_for_range(start, end):
    """
    Generator that yields dates from `start` to `end`, in 7 day intervals. End is inclusive.
    """
    infinite_date_generator = (start + timedelta(days=i) for i in itertools.count(step=7))
    return itertools.takewhile(lambda x: x <= end, infinite_date_generator)
