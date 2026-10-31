from datetime import date

from app.dao.fact_notification_status_live_dao import upsert_notification_status_live_counts
from app.models import FactNotificationStatusLive


def _dimensions(sample_job):
    return {
        "bst_date": date(2026, 8, 6),
        "service_id": sample_job.service.id,
        "template_id": sample_job.template.id,
        "job_id": sample_job.id,
        "key_type": "normal",
        "notification_type": sample_job.template.template_type,
        "notification_status": "delivered",
    }


def _count_change(dimensions, notification_count):
    return {**dimensions, "notification_count": notification_count}


def test_upsert_notification_status_live_counts_for_non_zero_change(notify_db_session, sample_job):
    dimensions = _dimensions(sample_job)

    upsert_notification_status_live_counts([_count_change(dimensions, 4)])
    row = notify_db_session.query(FactNotificationStatusLive).filter_by(**dimensions).one()

    assert row.notification_count == 4


def test_upsert_notification_status_live_counts_for_zero_change(notify_db_session, sample_job):
    dimensions = _dimensions(sample_job)

    upsert_notification_status_live_counts([_count_change(dimensions, 0)])
    row = notify_db_session.query(FactNotificationStatusLive).filter_by(**dimensions).first()

    assert row is None


def test_upsert_notification_status_live_counts_for_negative_change(notify_db_session, sample_job):
    dimensions = _dimensions(sample_job)

    # add initial count
    upsert_notification_status_live_counts([_count_change(dimensions, 4)])
    created_at = notify_db_session.query(FactNotificationStatusLive).filter_by(**dimensions).one().created_at

    # apply negative change
    upsert_notification_status_live_counts([_count_change(dimensions, -3)])
    row = notify_db_session.query(FactNotificationStatusLive).filter_by(**dimensions).one()

    assert row.notification_count == 1
    assert row.created_at == created_at
    assert row.updated_at is not None


def test_upsert_notification_status_live_counts_for_negative_change_below_zero(notify_db_session, sample_job):
    dimensions = _dimensions(sample_job)

    upsert_notification_status_live_counts([_count_change(dimensions, -5)])
    row = notify_db_session.query(FactNotificationStatusLive).filter_by(**dimensions).one()

    assert row.notification_count == -5


def test_upsert_notification_status_live_counts_for_multiple_changes(notify_db_session, sample_job):
    dimensions = _dimensions(sample_job)
    other_dimensions = {**dimensions, "notification_status": "failed"}

    upsert_notification_status_live_counts(
        [
            _count_change(dimensions, 4),
            _count_change(other_dimensions, 3),
        ]
    )

    rows = notify_db_session.query(FactNotificationStatusLive).all()

    assert len(rows) == 2
    assert notify_db_session.query(FactNotificationStatusLive).filter_by(**dimensions).one().notification_count == 4
    assert (
        notify_db_session.query(FactNotificationStatusLive).filter_by(**other_dimensions).one().notification_count == 3
    )


def test_upsert_existing_notification_status_live_counts_for_multiple_changes(notify_db_session, sample_job):
    dimensions = _dimensions(sample_job)
    other_dimensions = {**dimensions, "notification_status": "failed"}

    # add initial counts
    upsert_notification_status_live_counts(
        [
            _count_change(dimensions, 4),
            _count_change(other_dimensions, 3),
        ]
    )
    rows = notify_db_session.query(FactNotificationStatusLive).all()

    assert len(rows) == 2
    assert notify_db_session.query(FactNotificationStatusLive).filter_by(**dimensions).one().notification_count == 4
    assert (
        notify_db_session.query(FactNotificationStatusLive).filter_by(**other_dimensions).one().notification_count == 3
    )

    # apply additional changes
    upsert_notification_status_live_counts(
        [
            _count_change(dimensions, 2),
            _count_change(other_dimensions, -1),
        ]
    )
    new_rows = notify_db_session.query(FactNotificationStatusLive).all()

    assert len(new_rows) == 2
    assert notify_db_session.query(FactNotificationStatusLive).filter_by(**dimensions).one().notification_count == 6
    assert (
        notify_db_session.query(FactNotificationStatusLive).filter_by(**other_dimensions).one().notification_count == 2
    )
