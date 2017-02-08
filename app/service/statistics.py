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
