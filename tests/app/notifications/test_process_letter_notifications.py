import pytest

from app.dao.services_dao import dao_archive_service
from app.models import Job
from app.models import JOB_STATUS_READY_TO_SEND
from app.models import LETTER_TYPE
from app.models import Notification
from app.notifications.process_letter_notifications import create_letter_api_job
from app.notifications.process_letter_notifications import create_letter_notification
from app.v2.errors import InvalidRequest

from tests.app.db import create_service
from tests.app.db import create_template


def test_create_job_rejects_inactive_service(notify_db_session):
    service = create_service()
    template = create_template(service, template_type=LETTER_TYPE)
    dao_archive_service(service.id)

    with pytest.raises(InvalidRequest) as exc_info:
        create_letter_api_job(template)

    assert exc_info.value.message == 'Service {} is inactive'.format(service.id)


def test_create_job_rejects_archived_template(sample_letter_template):
    sample_letter_template.archived = True

    with pytest.raises(InvalidRequest) as exc_info:
        create_letter_api_job(sample_letter_template)

    assert exc_info.value.message == 'Template {} is deleted'.format(sample_letter_template.id)


def test_create_job_creates_job(sample_letter_template):
    job = create_letter_api_job(sample_letter_template)

    assert job == Job.query.one()
    assert job.original_file_name == 'letter submitted via api'
    assert job.service == sample_letter_template.service
    assert job.template_id == sample_letter_template.id
    assert job.template_version == sample_letter_template.version
    assert job.notification_count == 1
    assert job.job_status == JOB_STATUS_READY_TO_SEND
    assert job.created_by is None


def test_create_letter_notification_creates_notification(sample_letter_job, sample_api_key):
    data = {
        'personalisation': {
            'address_line_1': 'The Queen',
            'address_line_2': 'Buckingham Palace',
            'postcode': 'SW1 1AA',
        }
    }

    notification = create_letter_notification(data, sample_letter_job, sample_api_key)

    assert notification == Notification.query.one()
    assert notification.job == sample_letter_job
    assert notification.template == sample_letter_job.template
    assert notification.api_key == sample_api_key
    assert notification.notification_type == LETTER_TYPE
    assert notification.key_type == sample_api_key.key_type
    assert notification.job_row_number == 0
    assert notification.reference is not None
    assert notification.client_reference is None


def test_create_letter_notification_sets_reference(sample_letter_job, sample_api_key):
    data = {
        'personalisation': {
            'address_line_1': 'The Queen',
            'address_line_2': 'Buckingham Palace',
            'postcode': 'SW1 1AA',
        },
        'reference': 'foo'
    }

    notification = create_letter_notification(data, sample_letter_job, sample_api_key)

    assert notification.client_reference == 'foo'
