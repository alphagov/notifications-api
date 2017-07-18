from datetime import datetime
import uuid

from app.dao.jobs_dao import dao_create_job
from app.dao.provider_rates_dao import create_sms_rate
from app.dao.service_inbound_api_dao import save_service_inbound_api
from app.models import (
    Service,
    User,
    Template,
    Notification,
    ScheduledNotification,
    ServicePermission,
    Rate,
    Job,
    InboundSms,
    Organisation,
    EMAIL_TYPE,
    SMS_TYPE,
    KEY_TYPE_NORMAL,
    ServiceInboundApi)
from app.dao.users_dao import save_model_user
from app.dao.notifications_dao import dao_create_notification, dao_created_scheduled_notification
from app.dao.templates_dao import dao_create_template
from app.dao.services_dao import dao_create_service
from app.dao.service_permissions_dao import dao_add_service_permission
from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.dao.organisations_dao import dao_create_organisation


def create_user(mobile_number="+447700900986", email="notify@digital.cabinet-office.gov.uk", state='active'):
    data = {
        'id': uuid.uuid4(),
        'name': 'Test User',
        'email_address': email,
        'password': 'password',
        'mobile_number': mobile_number,
        'state': state
    }
    user = User.query.filter_by(email_address=email).first()
    if not user:
        user = User(**data)
    save_model_user(user)
    return user


def create_service(
    user=None,
    service_name="Sample service",
    service_id=None,
    restricted=False,
    service_permissions=[EMAIL_TYPE, SMS_TYPE],
    sms_sender='testing'
):
    service = Service(
        name=service_name,
        message_limit=1000,
        restricted=restricted,
        email_from=service_name.lower().replace(' ', '.'),
        created_by=user or create_user(),
        sms_sender=sms_sender
    )
    dao_create_service(service, service.created_by, service_id, service_permissions=service_permissions)
    return service


def create_template(
    service,
    template_type=SMS_TYPE,
    subject='Template subject',
    content='Dear Sir/Madam, Hello. Yours Truly, The Government.',
    template_id=None
):
    data = {
        'name': '{} Template Name'.format(template_type),
        'template_type': template_type,
        'content': content,
        'service': service,
        'created_by': service.created_by,
    }
    if template_type != SMS_TYPE:
        data['subject'] = subject
    template = Template(**data)
    dao_create_template(template)
    return template


def create_notification(
    template,
    job=None,
    job_row_number=None,
    to_field='+447700900855',
    status='created',
    reference=None,
    created_at=None,
    sent_at=None,
    updated_at=None,
    billable_units=1,
    personalisation=None,
    api_key_id=None,
    key_type=KEY_TYPE_NORMAL,
    sent_by=None,
    client_reference=None,
    rate_multiplier=None,
    international=False,
    phone_prefix=None,
    scheduled_for=None,
    normalised_to=None
):
    if created_at is None:
        created_at = datetime.utcnow()

    if status != 'created':
        sent_at = sent_at or datetime.utcnow()
        updated_at = updated_at or datetime.utcnow()

    data = {
        'id': uuid.uuid4(),
        'to': to_field,
        'job_id': job.id if job else None,
        'job': job,
        'service_id': template.service.id,
        'service': template.service,
        'template_id': template.id if template else None,
        'template': template,
        'template_version': template.version,
        'status': status,
        'reference': reference,
        'created_at': created_at,
        'sent_at': sent_at,
        'billable_units': billable_units,
        'personalisation': personalisation,
        'notification_type': template.template_type,
        'api_key_id': api_key_id,
        'key_type': key_type,
        'sent_by': sent_by,
        'updated_at': updated_at,
        'client_reference': client_reference,
        'job_row_number': job_row_number,
        'rate_multiplier': rate_multiplier,
        'international': international,
        'phone_prefix': phone_prefix,
        'normalised_to': normalised_to
    }
    notification = Notification(**data)
    dao_create_notification(notification)
    if scheduled_for:
        scheduled_notification = ScheduledNotification(id=uuid.uuid4(),
                                                       notification_id=notification.id,
                                                       scheduled_for=datetime.strptime(scheduled_for,
                                                                                       "%Y-%m-%d %H:%M"))
        if status != 'created':
            scheduled_notification.pending = False
        dao_created_scheduled_notification(scheduled_notification)
    return notification


def create_job(
    template,
    notification_count=1,
    created_at=None,
    job_status='pending',
    scheduled_for=None,
    processing_started=None,
    original_file_name='some.csv'
):
    data = {
        'id': uuid.uuid4(),
        'service_id': template.service_id,
        'service': template.service,
        'template_id': template.id,
        'template_version': template.version,
        'original_file_name': original_file_name,
        'notification_count': notification_count,
        'created_at': created_at or datetime.utcnow(),
        'created_by': template.created_by,
        'job_status': job_status,
        'scheduled_for': scheduled_for,
        'processing_started': processing_started
    }
    job = Job(**data)
    dao_create_job(job)
    return job


def create_service_permission(service_id, permission=EMAIL_TYPE):
    dao_add_service_permission(
        service_id if service_id else create_service().id, permission)

    service_permissions = ServicePermission.query.all()

    return service_permissions


def create_inbound_sms(
    service,
    notify_number=None,
    user_number='447700900111',
    provider_date=None,
    provider_reference=None,
    content='Hello',
    provider="mmg",
    created_at=None
):
    inbound = InboundSms(
        service=service,
        created_at=created_at or datetime.utcnow(),
        notify_number=notify_number or service.sms_sender,
        user_number=user_number,
        provider_date=provider_date or datetime.utcnow(),
        provider_reference=provider_reference or 'foo',
        content=content,
        provider=provider
    )
    dao_create_inbound_sms(inbound)
    return inbound


def create_service_inbound_api(
    service,
    url="https://something.com",
    bearer_token="some_super_secret",
):
    service_inbound_api = ServiceInboundApi(service_id=service.id,
                                            url=url,
                                            bearer_token=bearer_token,
                                            updated_by_id=service.users[0].id
                                            )
    save_service_inbound_api(service_inbound_api)
    return service_inbound_api


def create_organisation(colour='blue', logo='test_x2.png', name='test_org_1'):
    data = {
        'colour': colour,
        'logo': logo,
        'name': name
    }
    organisation = Organisation(**data)
    dao_create_organisation(organisation)

    return organisation


def create_rate(start_date, value, notification_type):
    rate = Rate(id=uuid.uuid4(), valid_from=start_date, rate=value, notification_type=notification_type)
    create_sms_rate(rate)
    return rate
