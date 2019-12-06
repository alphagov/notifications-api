from datetime import datetime, timedelta

from app.dao.uploads_dao import dao_get_uploads_by_service_id
from app.models import LETTER_TYPE, JOB_STATUS_IN_PROGRESS
from tests.app.db import create_job, create_service, create_template, create_notification


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


def test_get_uploads_for_service(sample_template):
    job = create_job(sample_template, processing_started=datetime.utcnow())
    letter_template = create_uploaded_template(sample_template.service)
    letter = create_uploaded_letter(letter_template, sample_template.service)

    other_service = create_service(service_name="other service")
    other_template = create_template(service=other_service)
    other_job = create_job(other_template, processing_started=datetime.utcnow())
    other_letter_template = create_uploaded_template(other_service)
    other_letter = create_uploaded_letter(other_letter_template, other_service)

    uploads_from_db = dao_get_uploads_by_service_id(job.service_id).items
    other_uploads_from_db = dao_get_uploads_by_service_id(other_job.service_id).items

    assert len(uploads_from_db) == 2

    assert uploads_from_db[0] == (letter.id, letter.client_reference, 1, letter.created_at,
                                  None, letter.created_at, letter.status, "letter")
    assert uploads_from_db[1] == (job.id, job.original_file_name, job.notification_count, job.created_at,
                                  job.scheduled_for, job.processing_started, job.job_status, "job")

    assert len(other_uploads_from_db) == 2
    assert other_uploads_from_db[0] == (other_letter.id,
                                        other_letter.client_reference,
                                        1,
                                        other_letter.created_at,
                                        None,
                                        other_letter.created_at,
                                        other_letter.status,
                                        "letter")
    assert other_uploads_from_db[1] == (other_job.id,
                                        other_job.original_file_name,
                                        other_job.notification_count,
                                        other_job.created_at,
                                        other_job.scheduled_for,
                                        other_job.processing_started,
                                        other_job.job_status, "job")

    assert uploads_from_db[0] != other_uploads_from_db[0]
    assert uploads_from_db[1] != other_uploads_from_db[1]


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
    upload_3 = create_uploaded_letter(letter_template, sample_template.service, status='delivered')

    results = dao_get_uploads_by_service_id(service_id=sample_template.service_id).items

    assert len(results) == 3
    assert results[0].id == upload_3.id
    assert results[1].id == upload_2.id
    assert results[2].id == upload_1.id


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


def test_get_uploads_orders_by_processing_started_and_created_at_desc(sample_template):
    letter_template = create_uploaded_template(sample_template.service)

    days_ago = datetime.utcnow() - timedelta(days=4)
    upload_1 = create_uploaded_letter(letter_template, service=letter_template.service)
    upload_2 = create_job(sample_template, processing_started=datetime.utcnow() - timedelta(days=1),
                          created_at=days_ago,
                          job_status=JOB_STATUS_IN_PROGRESS)
    upload_3 = create_job(sample_template, processing_started=datetime.utcnow() - timedelta(days=2),
                          created_at=days_ago,
                          job_status=JOB_STATUS_IN_PROGRESS)
    upload_4 = create_uploaded_letter(letter_template, service=letter_template.service,
                                      created_at=datetime.utcnow() - timedelta(days=3))

    results = dao_get_uploads_by_service_id(service_id=sample_template.service_id).items

    assert len(results) == 4
    assert results[0].id == upload_1.id
    assert results[1].id == upload_2.id
    assert results[2].id == upload_3.id
    assert results[3].id == upload_4.id


def test_get_uploads_is_paginated(sample_template):
    letter_template = create_uploaded_template(sample_template.service)

    upload_1 = create_uploaded_letter(letter_template, sample_template.service, status='delivered',
                                      created_at=datetime.utcnow() - timedelta(minutes=3))
    upload_2 = create_job(sample_template, processing_started=datetime.utcnow() - timedelta(minutes=2),
                          job_status=JOB_STATUS_IN_PROGRESS)
    upload_3 = create_uploaded_letter(letter_template, sample_template.service, status='delivered',
                                      created_at=datetime.utcnow() - timedelta(minutes=1))
    upload_4 = create_job(sample_template, processing_started=datetime.utcnow(), job_status=JOB_STATUS_IN_PROGRESS)

    results = dao_get_uploads_by_service_id(sample_template.service_id, page=1, page_size=2)

    assert results.per_page == 2
    assert results.total == 4
    assert len(results.items) == 2
    assert results.items[0].id == upload_4.id
    assert results.items[1].id == upload_3.id

    results = dao_get_uploads_by_service_id(sample_template.service_id, page=2, page_size=2)

    assert len(results.items) == 2
    assert results.items[0].id == upload_2.id
    assert results.items[1].id == upload_1.id


def test_get_uploads_returns_empty_list(sample_service):
    items = dao_get_uploads_by_service_id(sample_service.id).items
    assert items == []
