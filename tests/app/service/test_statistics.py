from datetime import datetime
import collections

import pytest
from freezegun import freeze_time

from app.service.statistics import (
    format_statistics,
    _weeks_for_range,
    create_zeroed_stats_dicts,
    format_weekly_notification_stats
)

StatsRow = collections.namedtuple('row', ('notification_type', 'status', 'count'))
WeeklyStatsRow = collections.namedtuple('row', ('notification_type', 'status', 'week_start', 'count'))


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


@pytest.mark.parametrize('start,end,dates', [
    (datetime(2016, 7, 25), datetime(2016, 7, 25), [datetime(2016, 7, 25)]),
    (datetime(2016, 7, 25), datetime(2016, 7, 28), [datetime(2016, 7, 25)]),
    (datetime(2016, 7, 25), datetime(2016, 8, 1), [datetime(2016, 7, 25), datetime(2016, 8, 1)]),
    (datetime(2016, 7, 25), datetime(2016, 8, 10), [
        datetime(2016, 7, 25), datetime(2016, 8, 1), datetime(2016, 8, 8)
    ])
])
def test_weeks_for_range(start, end, dates):
    assert list(_weeks_for_range(start, end)) == dates


def test_create_zeroed_stats_dicts():
    assert create_zeroed_stats_dicts() == {
        'sms': {'requested': 0, 'delivered': 0, 'failed': 0},
        'email': {'requested': 0, 'delivered': 0, 'failed': 0},
        'letter': {'requested': 0, 'delivered': 0, 'failed': 0},
    }


def _stats(requested, delivered, failed):
    return {'requested': requested, 'delivered': delivered, 'failed': failed}


@freeze_time('2016-07-28T12:00:00')
@pytest.mark.parametrize('created_at, statistics, expected_results', [
    # with no stats and just today, return this week's stats
    (datetime(2016, 7, 28), [], {
        datetime(2016, 7, 25): {
            'sms': _stats(0, 0, 0),
            'email': _stats(0, 0, 0),
            'letter': _stats(0, 0, 0)
        }
    }),
    # with a random created time, still create the dict for midnight
    (datetime(2016, 7, 28, 12, 13, 14), [], {
        datetime(2016, 7, 25, 0, 0, 0): {
            'sms': _stats(0, 0, 0),
            'email': _stats(0, 0, 0),
            'letter': _stats(0, 0, 0)
        }
    }),
    # with no stats but a service
    (datetime(2016, 7, 14), [], {
        datetime(2016, 7, 11): {
            'sms': _stats(0, 0, 0),
            'email': _stats(0, 0, 0),
            'letter': _stats(0, 0, 0)
        },
        datetime(2016, 7, 18): {
            'sms': _stats(0, 0, 0),
            'email': _stats(0, 0, 0),
            'letter': _stats(0, 0, 0)
        },
        datetime(2016, 7, 25): {
            'sms': _stats(0, 0, 0),
            'email': _stats(0, 0, 0),
            'letter': _stats(0, 0, 0)
        }
    }),
    # two stats for same week dont re-zero each other
    (datetime(2016, 7, 21), [
        WeeklyStatsRow('email', 'created', datetime(2016, 7, 18), 1),
        WeeklyStatsRow('sms', 'created', datetime(2016, 7, 18), 1),
        WeeklyStatsRow('letter', 'created', datetime(2016, 7, 18), 1),
    ], {
        datetime(2016, 7, 18): {
            'sms': _stats(1, 0, 0),
            'email': _stats(1, 0, 0),
            'letter': _stats(1, 0, 0)
        },
        datetime(2016, 7, 25): {
            'sms': _stats(0, 0, 0),
            'email': _stats(0, 0, 0),
            'letter': _stats(0, 0, 0)
        }
    }),
    # two stats for same type are added together
    (datetime(2016, 7, 21), [
        WeeklyStatsRow('sms', 'created', datetime(2016, 7, 18), 1),
        WeeklyStatsRow('sms', 'delivered', datetime(2016, 7, 18), 1),
        WeeklyStatsRow('sms', 'created', datetime(2016, 7, 25), 1),
    ], {
        datetime(2016, 7, 18): {
            'sms': _stats(2, 1, 0),
            'email': _stats(0, 0, 0),
            'letter': _stats(0, 0, 0)
        },
        datetime(2016, 7, 25): {
            'sms': _stats(1, 0, 0),
            'email': _stats(0, 0, 0),
            'letter': _stats(0, 0, 0)
        }
    })
])
def test_format_weekly_notification_stats(statistics, created_at, expected_results):
    assert format_weekly_notification_stats(statistics, created_at) == expected_results
