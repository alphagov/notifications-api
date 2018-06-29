import collections
from datetime import datetime
from unittest.mock import Mock

from freezegun import freeze_time
import pytest

from app.service.statistics import (
    format_admin_stats,
    format_statistics,
    create_stats_dict,
    create_zeroed_stats_dicts,
    create_empty_monthly_notification_status_stats_dict,
    add_monthly_notification_status_stats
)

StatsRow = collections.namedtuple('row', ('notification_type', 'status', 'count'))
NewStatsRow = collections.namedtuple('row', ('notification_type', 'status', 'key_type', 'count'))


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


def test_create_stats_dict():
    assert create_stats_dict() == {
        'sms': {'total': 0,
                'test-key': 0,
                'failures': {'technical-failure': 0,
                             'permanent-failure': 0,
                             'temporary-failure': 0,
                             'virus-scan-failed': 0}},
        'email': {'total': 0,
                  'test-key': 0,
                  'failures': {'technical-failure': 0,
                               'permanent-failure': 0,
                               'temporary-failure': 0,
                               'virus-scan-failed': 0}},
        'letter': {'total': 0,
                   'test-key': 0,
                   'failures': {'technical-failure': 0,
                                'permanent-failure': 0,
                                'temporary-failure': 0,
                                'virus-scan-failed': 0}}
    }


def test_format_admin_stats_only_includes_test_key_notifications_in_test_key_section():
    rows = [
        NewStatsRow('email', 'technical-failure', 'test', 3),
        NewStatsRow('sms', 'permanent-failure', 'test', 4),
        NewStatsRow('letter', 'virus-scan-failed', 'test', 5),
    ]
    stats_dict = format_admin_stats(rows)

    assert stats_dict['email']['total'] == 0
    assert stats_dict['email']['failures']['technical-failure'] == 0
    assert stats_dict['email']['test-key'] == 3

    assert stats_dict['sms']['total'] == 0
    assert stats_dict['sms']['failures']['permanent-failure'] == 0
    assert stats_dict['sms']['test-key'] == 4

    assert stats_dict['letter']['total'] == 0
    assert stats_dict['letter']['failures']['virus-scan-failed'] == 0
    assert stats_dict['letter']['test-key'] == 5


def test_format_admin_stats_counts_non_test_key_notifications_correctly():
    rows = [
        NewStatsRow('email', 'technical-failure', 'normal', 1),
        NewStatsRow('email', 'created', 'team', 3),
        NewStatsRow('sms', 'temporary-failure', 'normal', 6),
        NewStatsRow('sms', 'sent', 'normal', 2),
        NewStatsRow('letter', 'pending-virus-check', 'normal', 1),
    ]
    stats_dict = format_admin_stats(rows)

    assert stats_dict['email']['total'] == 4
    assert stats_dict['email']['failures']['technical-failure'] == 1

    assert stats_dict['sms']['total'] == 8
    assert stats_dict['sms']['failures']['permanent-failure'] == 0

    assert stats_dict['letter']['total'] == 1


def _stats(requested, delivered, failed):
    return {'requested': requested, 'delivered': delivered, 'failed': failed}


@pytest.mark.parametrize('year, expected_years', [
    (
        2018,
        [
            '2018-04',
            '2018-05',
            '2018-06'
        ]
    ),
    (
        2017,
        [
            '2017-04',
            '2017-05',
            '2017-06',
            '2017-07',
            '2017-08',
            '2017-09',
            '2017-10',
            '2017-11',
            '2017-12',
            '2018-01',
            '2018-02',
            '2018-03'
        ]
    )
])
@freeze_time('2018-05-31 23:59:59')
def test_create_empty_monthly_notification_status_stats_dict(year, expected_years):
    output = create_empty_monthly_notification_status_stats_dict(year)
    assert sorted(output.keys()) == expected_years
    for v in output.values():
        assert v == {'sms': {}, 'email': {}, 'letter': {}}


@freeze_time('2018-05-31 23:59:59')
def test_add_monthly_notification_status_stats():
    row_data = [
        {'month': datetime(2018, 4, 1), 'notification_type': 'sms', 'notification_status': 'sending', 'count': 1},
        {'month': datetime(2018, 4, 1), 'notification_type': 'sms', 'notification_status': 'delivered', 'count': 2},
        {'month': datetime(2018, 4, 1), 'notification_type': 'email', 'notification_status': 'sending', 'count': 4},
        {'month': datetime(2018, 5, 1), 'notification_type': 'sms', 'notification_status': 'sending', 'count': 8},
    ]
    rows = []
    for r in row_data:
        m = Mock(spec=[])
        for k, v in r.items():
            setattr(m, k, v)
        rows.append(m)

    data = create_empty_monthly_notification_status_stats_dict(2018)
    # this data won't be affected
    data['2018-05']['email']['sending'] = 32

    # this data will get overwritten
    data['2018-05']['sms']['sending'] = 16

    add_monthly_notification_status_stats(data, rows)

    assert data == {
        '2018-04': {'sms': {'sending': 1, 'delivered': 2}, 'email': {'sending': 4}, 'letter': {}},
        '2018-05': {'sms': {'sending': 8}, 'email': {'sending': 32}, 'letter': {}},
        '2018-06': {'sms': {}, 'email': {}, 'letter': {}},
    }
