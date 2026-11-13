from datetime import date

import pytest
from freezegun import freeze_time

from app import db
from app.constants import EMAIL_TYPE, SMS_TYPE
from app.dao.fact_notification_status_live_dao import (
    fetch_notification_status_live_for_service_for_today_and_7_previous_days,
    upsert_notification_status_live_counts,
)
from app.models import FactNotificationStatusLive
from tests.app.db import create_ft_notification_status_live, create_service, create_template
from tests.utils import QueryRecorder


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


@pytest.mark.parametrize(
    "session,expected_bind_key",
    (
        (db.session, None),
        (db.session_bulk, "bulk"),
    ),
)
@freeze_time("2018-10-31T18:00:00")
def test_fetch_notification_status_live_for_service_for_today_and_7_previous_days(
    notify_db_session, session, expected_bind_key
):
    service_1 = create_service(service_name="service_1")
    other_service = create_service(service_name="other_service")

    create_ft_notification_status_live(date(2018, 10, 31), "sms", service_1, count=4)
    create_ft_notification_status_live(date(2018, 10, 29), "sms", service_1, count=10)
    create_ft_notification_status_live(date(2018, 10, 29), "sms", service_1, notification_status="created")
    create_ft_notification_status_live(date(2018, 10, 29), "email", service_1, count=3)
    create_ft_notification_status_live(date(2018, 10, 26), "letter", service_1, count=5)

    # too early, shouldn't be included
    create_ft_notification_status_live(date(2018, 10, 23), "sms", service_1, count=8)
    # test keys shouldn't be included
    create_ft_notification_status_live(date(2018, 10, 29), "sms", service_1, key_type="test", count=7)
    # other services shouldn't be included
    create_ft_notification_status_live(date(2018, 10, 29), "sms", other_service, count=6)

    service_1_id = service_1.id
    with QueryRecorder() as query_recorder:
        results = sorted(
            fetch_notification_status_live_for_service_for_today_and_7_previous_days(service_1_id, session=session),
            key=lambda x: (x.notification_type, x.status),
        )

    assert {query_info.bind_key for query_info in query_recorder.queries} == {expected_bind_key}

    assert [(r.notification_type, r.status, r.count) for r in results] == [
        ("email", "delivered", 3),
        ("letter", "delivered", 5),
        ("sms", "created", 1),
        ("sms", "delivered", 14),
    ]


@pytest.mark.parametrize(
    "limit_days, expected_counts",
    [
        (0, [4]),
        (2, [4, 10]),
        (7, [4, 10, 8]),
    ],
)
@freeze_time("2018-10-31T18:00:00")
def test_fetch_notification_status_live_for_service_for_today_and_7_previous_days_respects_limit_days(
    notify_db_session, limit_days, expected_counts
):
    service = create_service()
    template = create_template(service=service)

    create_ft_notification_status_live(date(2018, 10, 31), template=template, count=4)
    create_ft_notification_status_live(date(2018, 10, 29), template=template, count=10, notification_status="failed")
    create_ft_notification_status_live(date(2018, 10, 24), template=template, count=8, notification_status="created")

    results = fetch_notification_status_live_for_service_for_today_and_7_previous_days(
        service.id, limit_days=limit_days
    )

    assert sorted(r.count for r in results) == sorted(expected_counts)


@pytest.mark.parametrize(
    "session,expected_bind_key",
    (
        (db.session, None),
        (db.session_bulk, "bulk"),
    ),
)
@freeze_time("2018-10-31T18:00:00")
def test_fetch_notification_status_live_by_template_for_service_for_today_and_7_previous_days(
    notify_db_session, session, expected_bind_key
):
    service_1 = create_service(service_name="service_1")
    sms_template = create_template(template_name="sms Template 1", service=service_1, template_type=SMS_TYPE)
    sms_template_2 = create_template(template_name="sms Template 2", service=service_1, template_type=SMS_TYPE)
    email_template = create_template(template_name="email Template", service=service_1, template_type=EMAIL_TYPE)

    # unused template
    create_template(template_name="unused", service=service_1, template_type=EMAIL_TYPE)

    create_ft_notification_status_live(date(2018, 10, 31), template=sms_template, count=2)
    create_ft_notification_status_live(date(2018, 10, 29), template=sms_template, count=10)
    create_ft_notification_status_live(date(2018, 10, 29), template=sms_template, notification_status="created")
    create_ft_notification_status_live(date(2018, 10, 29), template=sms_template_2, count=11)
    create_ft_notification_status_live(date(2018, 10, 29), template=email_template, count=3)

    # too early, shouldn't be included
    create_ft_notification_status_live(date(2018, 10, 23), template=sms_template, count=8)

    service_1_id = service_1.id
    with QueryRecorder() as query_recorder:
        results = fetch_notification_status_live_for_service_for_today_and_7_previous_days(
            service_1_id, by_template=True, session=session
        )

    assert {query_info.bind_key for query_info in query_recorder.queries} == {expected_bind_key}

    assert [
        ("email Template", False, email_template.id, "email", "delivered", 3),
        ("sms Template 1", False, sms_template.id, "sms", "created", 1),
        ("sms Template 1", False, sms_template.id, "sms", "delivered", 12),
        ("sms Template 2", False, sms_template_2.id, "sms", "delivered", 11),
    ] == sorted(results, key=lambda x: (x.notification_type, x.status, x.template_name))


@freeze_time("2018-10-31T18:00:00")
def test_fetch_notification_status_live_by_template_returns_is_precompiled_letter(notify_db_session):
    service = create_service()
    letter_template = create_template(
        service=service, template_type="letter", template_name="Pre-compiled PDF", hidden=True
    )
    create_ft_notification_status_live(date(2018, 10, 31), template=letter_template)

    results = fetch_notification_status_live_for_service_for_today_and_7_previous_days(service.id, by_template=True)

    assert [(r.template_name, r.is_precompiled_letter, r.template_id) for r in results] == [
        ("Pre-compiled PDF", True, letter_template.id)
    ]
