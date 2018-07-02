import collections

import pytest

from app.service.statistics import (
    format_admin_stats,
    format_statistics,
    create_stats_dict,
    create_zeroed_stats_dicts,
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
