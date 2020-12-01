from datetime import datetime, timedelta
from freezegun import freeze_time

from app.dao.uploads_dao import dao_get_uploads_by_service_id, dao_get_uploaded_letters_by_print_date
from app.models import LETTER_TYPE, JOB_STATUS_IN_PROGRESS
from tests.app.db import (
    create_job,
    create_service,
    create_service_data_retention,
    create_service_contact_list,
    create_template,
    create_notification,
)


def create_uploaded_letter(letter_template, service, status='created', created_at=None):
    return create_notification(
        template=letter_template,
        to_field="file-name",
        status=status,
        reference="dvla-reference",
        client_reference="file-name",
        one_off=True,
        created_by_id=service.users[0].id,
        created_at=created_at
    )


def create_uploaded_template(service):
    return create_template(
        service,
        template_type=LETTER_TYPE,
        template_name='Pre-compiled PDF',
        subject='Pre-compiled PDF',
        content="",
        hidden=True,
        postage="second",
    )


@freeze_time("2020-02-02 14:00")  # GMT time
def test_get_uploads_for_service(sample_template):
    create_service_data_retention(sample_template.service, 'sms', days_of_retention=9)
    contact_list = create_service_contact_list()
    # Jobs created from contact lists should be filtered out
    create_job(sample_template, contact_list_id=contact_list.id)
    job = create_job(sample_template, processing_started=datetime.utcnow())
    letter_template = create_uploaded_template(sample_template.service)
    letter = create_uploaded_letter(letter_template, sample_template.service)

    other_service = create_service(service_name="other service")
    other_template = create_template(service=other_service)
    other_job = create_job(other_template, processing_started=datetime.utcnow())
    other_letter_template = create_uploaded_template(other_service)
    create_uploaded_letter(other_letter_template, other_service)

    uploads_from_db = dao_get_uploads_by_service_id(job.service_id).items
    other_uploads_from_db = dao_get_uploads_by_service_id(other_job.service_id).items

    assert len(uploads_from_db) == 2

    assert uploads_from_db[0] == (
        None,
        'Uploaded letters',
        1,
        'letter',
        None,
        letter.created_at.replace(hour=17, minute=30, second=0, microsecond=0),
        None,
        letter.created_at.replace(hour=17, minute=30, second=0, microsecond=0),
        None,
        'letter_day',
        None,
    )
    assert uploads_from_db[1] == (
        job.id,
        job.original_file_name,
        job.notification_count,
        'sms',
        9,
        job.created_at,
        job.scheduled_for,
        job.processing_started,
        job.job_status,
        "job",
        None,
    )

    assert len(other_uploads_from_db) == 2
    assert other_uploads_from_db[0] == (
        None,
        'Uploaded letters',
        1,
        'letter',
        None,
        letter.created_at.replace(hour=17, minute=30, second=0, microsecond=0),
        None,
        letter.created_at.replace(hour=17, minute=30, second=0, microsecond=0),
        None,
        "letter_day",
        None,
    )
    assert other_uploads_from_db[1] == (other_job.id,
                                        other_job.original_file_name,
                                        other_job.notification_count,
                                        other_job.template.template_type,
                                        7,
                                        other_job.created_at,
                                        other_job.scheduled_for,
                                        other_job.processing_started,
                                        other_job.job_status,
                                        "job",
                                        None)

    assert uploads_from_db[1] != other_uploads_from_db[1]


@freeze_time("2020-02-02 18:00")
def test_get_uploads_for_service_groups_letters(sample_template):
    letter_template = create_uploaded_template(sample_template.service)

    # Just gets into yesterday’s print run
    create_uploaded_letter(letter_template, sample_template.service, created_at=(
        datetime(2020, 2, 1, 17, 29, 59)
    ))

    # Yesterday but in today’s print run
    create_uploaded_letter(letter_template, sample_template.service, created_at=(
        datetime(2020, 2, 1, 17, 30)
    ))
    # First thing today
    create_uploaded_letter(letter_template, sample_template.service, created_at=(
        datetime(2020, 2, 2, 0, 0)
    ))
    # Just before today’s print deadline
    create_uploaded_letter(letter_template, sample_template.service, created_at=(
        datetime(2020, 2, 2, 17, 29, 59)
    ))

    # Just missed today’s print deadline
    create_uploaded_letter(letter_template, sample_template.service, created_at=(
        datetime(2020, 2, 2, 17, 30)
    ))

    uploads_from_db = dao_get_uploads_by_service_id(sample_template.service_id).items

    assert [
        (upload.notification_count, upload.created_at)
        for upload in uploads_from_db
    ] == [
        (1, datetime(2020, 2, 3, 17, 30)),
        (3, datetime(2020, 2, 2, 17, 30)),
        (1, datetime(2020, 2, 1, 17, 30)),
    ]


def test_get_uploads_does_not_return_cancelled_jobs_or_letters(sample_template):
    create_job(sample_template, job_status='scheduled')
    create_job(sample_template, job_status='cancelled')
    letter_template = create_uploaded_template(sample_template.service)
    create_uploaded_letter(letter_template, sample_template.service, status='cancelled')

    assert len(dao_get_uploads_by_service_id(sample_template.service_id).items) == 0


def test_get_uploads_orders_by_created_at_desc(sample_template):
    letter_template = create_uploaded_template(sample_template.service)

    upload_1 = create_job(sample_template, processing_started=datetime.utcnow(),
                          job_status=JOB_STATUS_IN_PROGRESS)
    upload_2 = create_job(sample_template, processing_started=datetime.utcnow(),
                          job_status=JOB_STATUS_IN_PROGRESS)
    create_uploaded_letter(letter_template, sample_template.service, status='delivered')

    results = dao_get_uploads_by_service_id(service_id=sample_template.service_id).items

    assert [
        (result.id, result.upload_type) for result in results
    ] == [
        (None, 'letter_day'),
        (upload_2.id, 'job'),
        (upload_1.id, 'job'),
    ]


def test_get_uploads_orders_by_processing_started_desc(sample_template):
    days_ago = datetime.utcnow() - timedelta(days=3)
    upload_1 = create_job(sample_template, processing_started=datetime.utcnow() - timedelta(days=1),
                          created_at=days_ago,
                          job_status=JOB_STATUS_IN_PROGRESS)
    upload_2 = create_job(sample_template, processing_started=datetime.utcnow() - timedelta(days=2),
                          created_at=days_ago,
                          job_status=JOB_STATUS_IN_PROGRESS)

    results = dao_get_uploads_by_service_id(service_id=sample_template.service_id).items

    assert len(results) == 2
    assert results[0].id == upload_1.id
    assert results[1].id == upload_2.id


@freeze_time("2020-10-27 16:15")  # GMT time
def test_get_uploads_orders_by_processing_started_and_created_at_desc(sample_template):
    letter_template = create_uploaded_template(sample_template.service)

    days_ago = datetime.utcnow() - timedelta(days=4)
    create_uploaded_letter(letter_template, service=letter_template.service)
    upload_2 = create_job(sample_template, processing_started=datetime.utcnow() - timedelta(days=1),
                          created_at=days_ago,
                          job_status=JOB_STATUS_IN_PROGRESS)
    upload_3 = create_job(sample_template, processing_started=datetime.utcnow() - timedelta(days=2),
                          created_at=days_ago,
                          job_status=JOB_STATUS_IN_PROGRESS)
    create_uploaded_letter(letter_template, service=letter_template.service,
                           created_at=datetime.utcnow() - timedelta(days=3))

    results = dao_get_uploads_by_service_id(service_id=sample_template.service_id).items

    assert len(results) == 4
    assert results[0].id is None
    assert results[1].id == upload_2.id
    assert results[2].id == upload_3.id
    assert results[3].id is None


@freeze_time('2020-04-02 14:00')  # Few days after the clocks go forward
def test_get_uploads_only_gets_uploads_within_service_retention_period(sample_template):
    letter_template = create_uploaded_template(sample_template.service)
    create_service_data_retention(sample_template.service, 'sms', days_of_retention=3)

    days_ago = datetime.utcnow() - timedelta(days=4)
    upload_1 = create_uploaded_letter(letter_template, service=letter_template.service)
    upload_2 = create_job(
        sample_template, processing_started=datetime.utcnow() - timedelta(days=1), created_at=days_ago,
        job_status=JOB_STATUS_IN_PROGRESS
    )
    # older than custom retention for sms:
    create_job(
        sample_template, processing_started=datetime.utcnow() - timedelta(days=5), created_at=days_ago,
        job_status=JOB_STATUS_IN_PROGRESS
    )
    upload_3 = create_uploaded_letter(
        letter_template, service=letter_template.service, created_at=datetime.utcnow() - timedelta(days=3)
    )

    # older than retention for sms but within letter retention:
    upload_4 = create_uploaded_letter(
        letter_template, service=letter_template.service, created_at=datetime.utcnow() - timedelta(days=6)
    )

    # older than default retention for letters:
    create_uploaded_letter(
        letter_template, service=letter_template.service, created_at=datetime.utcnow() - timedelta(days=8)
    )

    results = dao_get_uploads_by_service_id(service_id=sample_template.service_id).items

    assert len(results) == 4

    # Uploaded letters get their `created_at` shifted time of printing
    # 17:30 BST == 16:30 UTC
    assert results[0].created_at == upload_1.created_at.replace(hour=16, minute=30, second=0, microsecond=0)

    # Jobs keep their original `created_at`
    assert results[1].created_at == upload_2.created_at.replace(hour=14, minute=00, second=0, microsecond=0)

    # Still in BST here…
    assert results[2].created_at == upload_3.created_at.replace(hour=16, minute=30, second=0, microsecond=0)

    # Now we’ve gone far enough back to be in GMT
    # 17:30 GMT == 17:30 UTC
    assert results[3].created_at == upload_4.created_at.replace(hour=17, minute=30, second=0, microsecond=0)


@freeze_time('2020-02-02 14:00')
def test_get_uploads_is_paginated(sample_template):
    letter_template = create_uploaded_template(sample_template.service)

    create_uploaded_letter(
        letter_template, sample_template.service, status='delivered',
        created_at=datetime.utcnow() - timedelta(minutes=3),
    )
    create_job(
        sample_template, processing_started=datetime.utcnow() - timedelta(minutes=2),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    create_uploaded_letter(
        letter_template, sample_template.service, status='delivered',
        created_at=datetime.utcnow() - timedelta(minutes=1),
    )
    create_job(
        sample_template, processing_started=datetime.utcnow(),
        job_status=JOB_STATUS_IN_PROGRESS,
    )

    results = dao_get_uploads_by_service_id(sample_template.service_id, page=1, page_size=1)

    assert results.per_page == 1
    assert results.total == 3
    assert len(results.items) == 1
    assert results.items[0].created_at == datetime.utcnow().replace(hour=17, minute=30, second=0, microsecond=0)
    assert results.items[0].notification_count == 2
    assert results.items[0].upload_type == 'letter_day'

    results = dao_get_uploads_by_service_id(sample_template.service_id, page=2, page_size=1)

    assert len(results.items) == 1
    assert results.items[0].created_at == datetime.utcnow().replace(hour=14, minute=0, second=0, microsecond=0)
    assert results.items[0].notification_count == 1
    assert results.items[0].upload_type == 'job'


def test_get_uploads_returns_empty_list(sample_service):
    items = dao_get_uploads_by_service_id(sample_service.id).items
    assert items == []


@freeze_time('2020-02-02 14:00')
def test_get_uploaded_letters_by_print_date(sample_template):
    letter_template = create_uploaded_template(sample_template.service)

    # Letters for the previous day’s run
    for i in range(3):
        create_uploaded_letter(
            letter_template, sample_template.service, status='delivered',
            created_at=datetime.utcnow().replace(day=1, hour=17, minute=29, second=59)
        )

    # Letters from yesterday that rolled into today’s run
    for i in range(30):
        create_uploaded_letter(
            letter_template, sample_template.service, status='delivered',
            created_at=datetime.utcnow().replace(day=1, hour=17, minute=30, second=0)
        )

    # Letters that just made today’s run
    for i in range(30):
        create_uploaded_letter(
            letter_template, sample_template.service, status='delivered',
            created_at=datetime.utcnow().replace(hour=17, minute=29, second=59)
        )

    # Letters that just missed today’s run
    for i in range(3):
        create_uploaded_letter(
            letter_template, sample_template.service, status='delivered',
            created_at=datetime.utcnow().replace(hour=17, minute=30, second=0)
        )

    result = dao_get_uploaded_letters_by_print_date(
        sample_template.service_id,
        datetime.utcnow(),
    )
    assert result.total == 60
    assert len(result.items) == 50
    assert result.has_next is True
    assert result.has_prev is False

    result = dao_get_uploaded_letters_by_print_date(
        sample_template.service_id,
        datetime.utcnow(),
        page=10,
        page_size=2,
    )
    assert result.total == 60
    assert len(result.items) == 2
    assert result.has_next is True
    assert result.has_prev is True
