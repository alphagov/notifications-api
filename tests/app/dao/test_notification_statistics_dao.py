from datetime import (date, timedelta)

from app.models import NotificationStatistics
from tests.app.conftest import sample_notification_statistics as create_sample_notification_statistics
from app.dao.notifications_dao import dao_get_7_day_agg_notification_statistics_for_service


def test_display_weekly_notification_statistics_sum_over_week(notify_db,
                                                              notify_db_session,
                                                              sample_service):
    fools = date(2016, 4, 1)
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=fools
    )
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=fools + timedelta(days=1)
    )
    assert dao_get_7_day_agg_notification_statistics_for_service(
        sample_service.id,
        fools
    ).all() == [(0, 4, 2, 2, 4, 2, 2)]


def test_display_weekly_notification_statistics_separate_over_weeks(notify_db,
                                                                    notify_db_session,
                                                                    sample_service):
    fools = date(2016, 4, 1)
    next_week = fools + timedelta(days=7)
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=fools
    )
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=next_week
    )
    assert dao_get_7_day_agg_notification_statistics_for_service(
        sample_service.id,
        fools
    ).all() == [(1, 2, 1, 1, 2, 1, 1), (0, 2, 1, 1, 2, 1, 1)]


def test_display_weekly_notification_statistics_7_days_from_date_from(notify_db,
                                                                      notify_db_session,
                                                                      sample_service):
    fools = date(2016, 4, 1)
    eow_fools = fools + timedelta(days=6)
    next_week = fools + timedelta(days=7)
    two_weeks_later = fools + timedelta(days=14)
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=fools
    )
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=eow_fools
    )
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=next_week
    )
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=two_weeks_later
    )
    assert dao_get_7_day_agg_notification_statistics_for_service(
        sample_service.id,
        fools
    ).all() == [(2, 2, 1, 1, 2, 1, 1), (1, 2, 1, 1, 2, 1, 1), (0, 4, 2, 2, 4, 2, 2)]


def test_display_weekly_notification_statistics_week_number_misses_week(notify_db,
                                                                        notify_db_session,
                                                                        sample_service):
    fools = date(2016, 4, 1)
    two_weeks_later = fools + timedelta(days=14)
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=fools
    )
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=two_weeks_later
    )
    assert dao_get_7_day_agg_notification_statistics_for_service(
        sample_service.id,
        fools
    ).all() == [(2, 2, 1, 1, 2, 1, 1), (0, 2, 1, 1, 2, 1, 1)]


def test_display_weekly_notification_statistics_week_limit(notify_db,
                                                           notify_db_session,
                                                           sample_service):
    fools = date(2016, 4, 1)
    two_weeks_later = fools + timedelta(days=14)
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=fools
    )
    create_sample_notification_statistics(
        notify_db,
        notify_db_session,
        day=two_weeks_later
    )
    assert dao_get_7_day_agg_notification_statistics_for_service(
        sample_service.id,
        fools,
        1
    ).all() == [(0, 2, 1, 1, 2, 1, 1)]
