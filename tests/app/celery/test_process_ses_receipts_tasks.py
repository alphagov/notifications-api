import json
from datetime import datetime

from app.celery.process_ses_receipts_tasks import process_ses_results
from app.models import Complaint
from app.notifications.notifications_ses_callback import remove_emails_from_complaint

from tests.app.db import (
    create_notification, ses_complaint_callback,
    ses_notification_callback,
)


def test_process_ses_results(sample_email_template):
    create_notification(
        sample_email_template,
        reference='ref1',
        sent_at=datetime.utcnow(),
        status='sending')

    response = json.loads(ses_notification_callback())
    assert process_ses_results(response=response) is None


def test_process_ses_results_does_not_retry_if_errors(notify_db, mocker):
    mocked = mocker.patch('app.celery.process_ses_receipts_tasks.process_ses_results.retry')
    response = json.loads(ses_notification_callback())
    process_ses_results(response=response)
    assert mocked.call_count == 0


def test_process_ses_results_retry_called(notify_db, mocker):
    mocker.patch("app.dao.notifications_dao.update_notification_status_by_reference", side_effect=Exception("EXPECTED"))
    mocked = mocker.patch('app.celery.process_ses_receipts_tasks.process_ses_results.retry')
    response = json.loads(ses_notification_callback())
    process_ses_results(response=response)
    assert mocked.call_count != 0


def test_process_ses_results_in_complaint(sample_email_template, mocker):
    notification = create_notification(template=sample_email_template, reference='ref1')
    mocked = mocker.patch("app.dao.notifications_dao.update_notification_status_by_reference")
    process_ses_results(response=ses_complaint_callback())
    assert mocked.call_count == 0
    complaints = Complaint.query.all()
    assert len(complaints) == 1
    assert complaints[0].notification_id == notification.id


def test_remove_emails_from_complaint():
    test_json = json.loads(ses_complaint_callback()['Message'])
    remove_emails_from_complaint(test_json)
    assert "recipient1@example.com" not in test_json
