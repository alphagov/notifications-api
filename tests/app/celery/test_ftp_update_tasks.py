from datetime import datetime

import pytest
from freezegun import freeze_time
from flask import current_app

from app.models import (
    Job,
    Notification,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_TECHNICAL_FAILURE
)
from app.celery.tasks import (
    process_updates_from_file,
    update_dvla_job_to_error,
    update_job_to_sent_to_dvla,
    update_letter_notifications_statuses,
    update_letter_notifications_to_error,
    update_letter_notifications_to_sent_to_dvla
)

from tests.app.db import create_notification, create_service_callback_api
from tests.conftest import set_config


def test_update_job_to_sent_to_dvla(sample_letter_template, sample_letter_job):
    create_notification(template=sample_letter_template, job=sample_letter_job)
    create_notification(template=sample_letter_template, job=sample_letter_job)
    update_job_to_sent_to_dvla(job_id=sample_letter_job.id)

    updated_notifications = Notification.query.all()
    assert [(n.status == 'sending', n.sent_by == 'dvla') for n in updated_notifications]

    assert Job.query.filter_by(id=sample_letter_job.id).one().job_status == 'sent to dvla'


def test_update_dvla_job_to_error(sample_letter_template, sample_letter_job):
    create_notification(template=sample_letter_template, job=sample_letter_job)
    create_notification(template=sample_letter_template, job=sample_letter_job)
    update_dvla_job_to_error(job_id=sample_letter_job.id)

    updated_notifications = Notification.query.all()
    for n in updated_notifications:
        assert n.status == 'created'
        assert not n.sent_by

    assert Job.query.filter_by(id=sample_letter_job.id).one().job_status == 'error'


def test_update_letter_notifications_statuses_raises_for_invalid_format(notify_api, mocker):
    invalid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=invalid_file)

    with pytest.raises(TypeError):
        update_letter_notifications_statuses(filename='foo.txt')


def test_update_letter_notifications_statuses_calls_with_correct_bucket_location(notify_api, mocker):
    s3_mock = mocker.patch('app.celery.tasks.s3.get_s3_object')

    with set_config(notify_api, 'NOTIFY_EMAIL_DOMAIN', 'foo.bar'):
        update_letter_notifications_statuses(filename='foo.txt')
        s3_mock.assert_called_with('{}-ftp'.format(current_app.config['NOTIFY_EMAIL_DOMAIN']), 'foo.txt')


def test_update_letter_notifications_statuses_builds_updates_from_content(notify_api, mocker):
    valid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)
    update_mock = mocker.patch('app.celery.tasks.process_updates_from_file')

    update_letter_notifications_statuses(filename='foo.txt')

    update_mock.assert_called_with('ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted')


def test_update_letter_notifications_statuses_builds_updates_list(notify_api, mocker):
    valid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted'
    updates = process_updates_from_file(valid_file)

    assert len(updates) == 2

    assert updates[0].reference == 'ref-foo'
    assert updates[0].status == 'Sent'
    assert updates[0].page_count == '1'
    assert updates[0].cost_threshold == 'Unsorted'

    assert updates[1].reference == 'ref-bar'
    assert updates[1].status == 'Sent'
    assert updates[1].page_count == '2'
    assert updates[1].cost_threshold == 'Sorted'


def test_update_letter_notifications_statuses_persisted(notify_api, mocker, sample_letter_template):
    sent_letter = create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING,
                                      billable_units=0)
    failed_letter = create_notification(sample_letter_template, reference='ref-bar', status=NOTIFICATION_SENDING,
                                        billable_units=0)
    create_service_callback_api(service=sample_letter_template.service, url="https://original_url.com")
    valid_file = '{}|Sent|1|Unsorted\n{}|Failed|2|Sorted'.format(
        sent_letter.reference, failed_letter.reference)
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)

    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )

    update_letter_notifications_statuses(filename='foo.txt')

    assert sent_letter.status == NOTIFICATION_DELIVERED
    assert sent_letter.billable_units == 1
    assert sent_letter.updated_at
    assert failed_letter.status == NOTIFICATION_TECHNICAL_FAILURE
    assert failed_letter.billable_units == 2
    assert failed_letter.updated_at
    assert send_mock.called


def test_update_letter_notifications_to_sent_to_dvla_updates_based_on_notification_references(
    client,
    sample_letter_template
):
    first = create_notification(sample_letter_template, reference='first ref')
    second = create_notification(sample_letter_template, reference='second ref')

    dt = datetime.utcnow()
    with freeze_time(dt):
        update_letter_notifications_to_sent_to_dvla([first.reference])

    assert first.status == NOTIFICATION_SENDING
    assert first.sent_by == 'dvla'
    assert first.sent_at == dt
    assert first.updated_at == dt
    assert second.status == NOTIFICATION_CREATED


def test_update_letter_notifications_to_error_updates_based_on_notification_references(
    client,
    sample_letter_template,
    mocker
):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    first = create_notification(sample_letter_template, reference='first ref')
    second = create_notification(sample_letter_template, reference='second ref')
    create_service_callback_api(service=sample_letter_template.service, url="https://original_url.com")
    dt = datetime.utcnow()
    with freeze_time(dt):
        update_letter_notifications_to_error([first.reference])

    assert first.status == NOTIFICATION_TECHNICAL_FAILURE
    assert first.sent_by is None
    assert first.sent_at is None
    assert first.updated_at == dt
    assert second.status == NOTIFICATION_CREATED
    assert send_mock.called
