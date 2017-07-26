from app import create_random_identifier
from app.models import LETTER_TYPE, JOB_STATUS_READY_TO_SEND
from app.notifications.process_notifications import persist_notification


def create_letter_api_job(template):
    service = template.service
    if not service.active:
        raise InvalidRequest('Create job is not allowed: service is inactive', 403)
    if template.archived:
        raise InvalidRequest('Create job is not allowed: template is deleted', 400)


    job = Job(
        original_file_name='letter submitted via api',
        service=service,
        template=template,
        template_version=template.version,
        notification_count=1,
        job_status=JOB_STATUS_READY_TO_SEND,
        created_by=None
    )
    dao_create_job(job)


def create_letter_notification(letter_data, job, api_key):
    notification = persist_notification(
        template_id=job.template.id,
        template_version=job.template.version,
        recipient=letter_data['personalisation']['address line 1'],  # or addressline1 or address_line_1?
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
