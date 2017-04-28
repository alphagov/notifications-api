from datetime import datetime
import collections

import pytest
from freezegun import freeze_time

from app.service.statistics import (
    format_statistics,
    create_zeroed_stats_dicts,
)

StatsRow = collections.namedtuple('row', ('notification_type', 'status', 'count'))


# email_counts and sms_counts are 3-tuple of requested, delivered, failed
@pytest.mark.idparametrize('stats, email_counts, sms_counts, letter_counts', {
    'empty': ([], [0, 0, 0], [0, 0, 0], [0, 0, 0]),
    'always_increment_requested': ([
        StatsRow('email', 'delivered', 1),
        StatsRow('email', 'failed', 1)
    ], [2, 1, 1], [0, 0, 0], [0, 0, 0]),
    'dont_mix_template_types': ([
        StatsRow('email', 'delivered', 1),
        StatsRow('sms', 'delivered', 1),
        StatsRow('letter', 'delivered', 1)
    ], [1, 1, 0], [1, 1, 0], [1, 1, 0]),
    'convert_fail_statuses_to_failed': ([
        StatsRow('email', 'failed', 1),
        StatsRow('email', 'technical-failure', 1),
        StatsRow('email', 'temporary-failure', 1),
        StatsRow('email', 'permanent-failure', 1),
    ], [4, 0, 4], [0, 0, 0], [0, 0, 0]),
    'convert_sent_to_delivered': ([
        StatsRow('sms', 'sending', 1),
        StatsRow('sms', 'delivered', 1),
        StatsRow('sms', 'sent', 1),
    ], [0, 0, 0], [3, 2, 0], [0, 0, 0]),
})
def test_format_statistics(stats, email_counts, sms_counts, letter_counts):

    ret = format_statistics(stats)

    assert ret['email'] == {
        status: count
        for status, count
        in zip(['requested', 'delivered', 'failed'], email_counts)
    }

    assert ret['sms'] == {
        status: count
        for status, count
        in zip(['requested', 'delivered', 'failed'], sms_counts)
    }

    assert ret['letter'] == {
        status: count
        for status, count
        in zip(['requested', 'delivered', 'failed'], letter_counts)
    }


def test_create_zeroed_stats_dicts():
    assert create_zeroed_stats_dicts() == {
        'sms': {'requested': 0, 'delivered': 0, 'failed': 0},
        'email': {'requested': 0, 'delivered': 0, 'failed': 0},
        'letter': {'requested': 0, 'delivered': 0, 'failed': 0},
    }


def _stats(requested, delivered, failed):
    return {'requested': requested, 'delivered': delivered, 'failed': failed}
