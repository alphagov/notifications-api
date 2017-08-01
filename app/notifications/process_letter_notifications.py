from app import create_random_identifier
from app.models import LETTER_TYPE, JOB_STATUS_READY_TO_SEND, Job
from app.dao.jobs_dao import dao_create_job
from app.notifications.process_notifications import persist_notification
from app.v2.errors import InvalidRequest
from app.variables import LETTER_API_FILENAME


def create_letter_api_job(template):
    service = template.service
    if not service.active:
        raise InvalidRequest('Service {} is inactive'.format(service.id), 403)
    if template.archived:
        raise InvalidRequest('Template {} is deleted'.format(template.id), 400)

    job = Job(
        original_file_name=LETTER_API_FILENAME,
        service=service,
        template=template,
        template_version=template.version,
        notification_count=1,
        job_status=JOB_STATUS_READY_TO_SEND,
        created_by=None
    )
    dao_create_job(job)
    return job


def create_letter_notification(letter_data, job, api_key):
    notification = persist_notification(
        template_id=job.template.id,
        template_version=job.template.version,
        # we only accept addresses_with_underscores from the API (from CSV we also accept dashes, spaces etc)
        recipient=letter_data['personalisation']['address_line_1'],
        service=job.service,
        personalisation=letter_data['personalisation'],
        notification_type=LETTER_TYPE,
        api_key_id=api_key.id,
        key_type=api_key.key_type,
        job_id=job.id,
        job_row_number=0,
        reference=create_random_identifier(),
        client_reference=letter_data.get('reference')
    )
    return notification
