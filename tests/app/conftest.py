import uuid
from datetime import (datetime, date, timedelta)

import requests_mock
import pytest
from flask import current_app

from app import db
from app.models import (
    User,
    Service,
    Template,
    ApiKey,
    Job,
    Notification,
    NotificationHistory,
    InvitedUser,
    Permission,
    ProviderStatistics,
    ProviderDetails,
    NotificationStatistics,
    ServiceWhitelist,
    KEY_TYPE_NORMAL, KEY_TYPE_TEST, KEY_TYPE_TEAM,
    MOBILE_TYPE, EMAIL_TYPE)
from app.dao.users_dao import (save_model_user, create_user_code, create_secret_code)
from app.dao.services_dao import (dao_create_service, dao_add_user_to_service)
from app.dao.templates_dao import dao_create_template
from app.dao.api_key_dao import save_model_api_key
from app.dao.jobs_dao import dao_create_job
from app.dao.notifications_dao import dao_create_notification
from app.dao.invited_user_dao import save_invited_user
from app.dao.provider_rates_dao import create_provider_rates
from app.clients.sms.firetext import FiretextClient


@pytest.yield_fixture
def rmock():
    with requests_mock.mock() as rmock:
        yield rmock


@pytest.fixture(scope='function')
def service_factory(notify_db, notify_db_session):
    class ServiceFactory(object):
        def get(self, service_name, user=None, template_type=None, email_from=None):
            if not user:
                user = sample_user(notify_db, notify_db_session)
            if not email_from:
                email_from = service_name
            service = sample_service(notify_db, notify_db_session, service_name, user, email_from=email_from)
            if template_type == 'email':
                sample_template(
                    notify_db,
                    notify_db_session,
                    template_type=template_type,
                    subject_line=service.email_from,
                    service=service
                )
            else:
                sample_template(
                    notify_db,
                    notify_db_session,
                    service=service
                )
            return service

    return ServiceFactory()


@pytest.fixture(scope='function')
def sample_user(notify_db,
                notify_db_session,
                mobile_numnber="+447700900986",
                email="notify@digital.cabinet-office.gov.uk"):
    data = {
        'name': 'Test User',
        'email_address': email,
        'password': 'password',
        'mobile_number': mobile_numnber,
        'state': 'active'
    }
    usr = User.query.filter_by(email_address=email).first()
    if not usr:
        usr = User(**data)
        save_model_user(usr)

    return usr


def create_code(notify_db, notify_db_session, code_type, usr=None, code=None):
    if code is None:
        code = create_secret_code()
    if usr is None:
        usr = sample_user(notify_db, notify_db_session)
    return create_user_code(usr, code, code_type), code


@pytest.fixture(scope='function')
def sample_email_code(notify_db,
                      notify_db_session,
                      code=None,
                      code_type="email",
                      usr=None):
    code, txt_code = create_code(notify_db,
                                 notify_db_session,
                                 code_type,
                                 usr=usr,
                                 code=code)
    code.txt_code = txt_code
    return code


@pytest.fixture(scope='function')
def sample_sms_code(notify_db,
                    notify_db_session,
                    code=None,
                    code_type="sms",
                    usr=None):
    code, txt_code = create_code(notify_db,
                                 notify_db_session,
                                 code_type,
                                 usr=usr,
                                 code=code)
    code.txt_code = txt_code
    return code


@pytest.fixture(scope='function')
def sample_service(notify_db,
                   notify_db_session,
                   service_name="Sample service",
                   user=None,
                   active=True,
                   restricted=False,
                   limit=1000,
                   email_from=None):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    if email_from is None:
        email_from = service_name.lower().replace(' ', '.')
    data = {
        'name': service_name,
        'message_limit': limit,
        'active': active,
        'restricted': restricted,
        'email_from': email_from,
        'created_by': user
    }
    service = Service.query.filter_by(name=service_name).first()
    if not service:
        service = Service(**data)
        dao_create_service(service, user)
    else:
        if user not in service.users:
            dao_add_user_to_service(service, user)
    return service


@pytest.fixture(scope='function')
def sample_template(notify_db,
                    notify_db_session,
                    template_name="Template Name",
                    template_type="sms",
                    content="This is a template:\nwith a newline",
                    archived=False,
                    subject_line='Subject',
                    user=None,
                    service=None,
                    created_by=None):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if created_by is None:
        created_by = sample_user(notify_db, notify_db_session)
    data = {
        'name': template_name,
        'template_type': template_type,
        'content': content,
        'service': service,
        'created_by': created_by,
        'archived': archived
    }
    if template_type in ['email', 'letter']:
        data.update({
            'subject': subject_line
        })
    template = Template(**data)
    dao_create_template(template)
    return template


@pytest.fixture(scope='function')
def sample_template_with_placeholders(notify_db, notify_db_session):
    # deliberate space and title case in placeholder
    return sample_template(notify_db, notify_db_session, content="Hello (( Name))\nYour thing is due soon")


@pytest.fixture(scope='function')
def sample_email_template(
        notify_db,
        notify_db_session,
        template_name="Email Template Name",
        template_type="email",
        user=None,
        content="This is a template",
        subject_line='Email Subject',
        service=None):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    data = {
        'name': template_name,
        'template_type': template_type,
        'content': content,
        'service': service,
        'created_by': user
    }
    if subject_line:
        data.update({
            'subject': subject_line
        })
    template = Template(**data)
    dao_create_template(template)
    return template


@pytest.fixture(scope='function')
def sample_email_template_with_placeholders(notify_db, notify_db_session):
    return sample_email_template(
        notify_db,
        notify_db_session,
        content="Hello ((name))\nThis is an email from GOV.UK",
        subject_line="((name))")


@pytest.fixture(scope='function')
def sample_api_key(notify_db,
                   notify_db_session,
                   service=None,
                   key_type=KEY_TYPE_NORMAL,
                   name=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    data = {'service': service, 'name': name or uuid.uuid4(), 'created_by': service.created_by, 'key_type': key_type}
    api_key = ApiKey(**data)
    save_model_api_key(api_key)
    return api_key


@pytest.fixture(scope='function')
def sample_test_api_key(notify_db, notify_db_session, service=None):
    return sample_api_key(notify_db, notify_db_session, service, KEY_TYPE_TEST)


@pytest.fixture(scope='function')
def sample_team_api_key(notify_db, notify_db_session, service=None):
    return sample_api_key(notify_db, notify_db_session, service, KEY_TYPE_TEAM)


@pytest.fixture(scope='function')
def sample_job(notify_db,
               notify_db_session,
               service=None,
               template=None,
               notification_count=1,
               created_at=None,
               job_status='pending',
               scheduled_for=None,
               processing_started=None,
               original_file_name='some.csv'):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if template is None:
        template = sample_template(notify_db, notify_db_session,
                                   service=service)
    data = {
        'id': uuid.uuid4(),
        'service_id': service.id,
        'service': service,
        'template_id': template.id,
        'template_version': template.version,
        'original_file_name': original_file_name,
        'notification_count': notification_count,
        'created_at': created_at or datetime.utcnow(),
        'created_by': service.created_by,
        'job_status': job_status,
        'scheduled_for': scheduled_for,
        'processing_started': processing_started
    }
    job = Job(**data)
    dao_create_job(job)
    return job


@pytest.fixture(scope='function')
def sample_job_with_placeholdered_template(
        notify_db,
        notify_db_session,
        service=None
):
    return sample_job(
        notify_db,
        notify_db_session,
        service=service,
        template=sample_template_with_placeholders(notify_db, notify_db_session)
    )


@pytest.fixture(scope='function')
def sample_scheduled_job(
    notify_db,
    notify_db_session,
    service=None
):
    return sample_job(
        notify_db,
        notify_db_session,
        service=service,
        template=sample_template_with_placeholders(notify_db, notify_db_session),
        scheduled_for=(datetime.utcnow() + timedelta(minutes=60)).isoformat(),
        job_status='scheduled'
    )


@pytest.fixture(scope='function')
def sample_email_job(notify_db,
                     notify_db_session,
                     service=None,
                     template=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if template is None:
        template = sample_email_template(
            notify_db,
            notify_db_session,
            service=service)
    job_id = uuid.uuid4()
    data = {
        'id': job_id,
        'service_id': service.id,
        'service': service,
        'template_id': template.id,
        'template_version': template.version,
        'original_file_name': 'some.csv',
        'notification_count': 1,
        'created_by': service.created_by
    }
    job = Job(**data)
    dao_create_job(job)
    return job


@pytest.fixture(scope='function')
def sample_notification_with_job(
        notify_db,
        notify_db_session,
        service=None,
        template=None,
        job=None,
        job_row_number=None,
        to_field=None,
        status='created',
        reference=None,
        created_at=None,
        sent_at=None,
        billable_units=1,
        create=True,
        personalisation=None,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL
):
    if job is None:
        job = sample_job(notify_db, notify_db_session, service=service, template=template)

    return sample_notification(
        notify_db,
        notify_db_session,
        service,
        template,
        job=job,
        job_row_number=job_row_number if job_row_number else None,
        to_field=to_field,
        status=status,
        reference=reference,
        created_at=created_at,
        sent_at=sent_at,
        billable_units=billable_units,
        create=create,
        personalisation=personalisation,
        api_key_id=api_key_id,
        key_type=key_type
    )


@pytest.fixture(scope='function')
def sample_notification(notify_db,
                        notify_db_session,
                        service=None,
                        template=None,
                        job=None,
                        job_row_number=None,
                        to_field=None,
                        status='created',
                        reference=None,
                        created_at=None,
                        sent_at=None,
                        billable_units=1,
                        create=True,
                        personalisation=None,
                        api_key_id=None,
                        key_type=KEY_TYPE_NORMAL,
                        sent_by=None):
    if created_at is None:
        created_at = datetime.utcnow()
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if template is None:
        template = sample_template(notify_db, notify_db_session, service=service)

    notification_id = uuid.uuid4()

    if to_field:
        to = to_field
    else:
        to = '+447700900855'

    data = {
        'id': notification_id,
        'to': to,
        'job_id': job.id if job else None,
        'job': job,
        'service_id': service.id,
        'service': service,
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
        'sent_by': sent_by
    }
    if job_row_number:
        data['job_row_number'] = job_row_number
    notification = Notification(**data)
    if create:
        dao_create_notification(notification)
    return notification


@pytest.fixture(scope='function')
def sample_notification_with_api_key(notify_db, notify_db_session):
    notification = sample_notification(notify_db, notify_db_session)
    notification.api_key_id = sample_api_key(
        notify_db,
        notify_db_session,
        name='Test key'
    ).id
    return notification


@pytest.fixture(scope='function')
def sample_email_notification(notify_db, notify_db_session):
    created_at = datetime.utcnow()
    service = sample_service(notify_db, notify_db_session)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, service=service, template=template)

    notification_id = uuid.uuid4()

    to = 'foo@bar.com'

    data = {
        'id': notification_id,
        'to': to,
        'job_id': job.id,
        'job': job,
        'service_id': service.id,
        'service': service,
        'template': template,
        'template_version': template.version,
        'status': 'created',
        'reference': None,
        'created_at': created_at,
        'billable_units': 0,
        'personalisation': None,
        'notification_type': template.template_type,
        'api_key_id': None,
        'key_type': KEY_TYPE_NORMAL,
        'job_row_number': 1
    }
    notification = Notification(**data)
    dao_create_notification(notification)
    return notification


@pytest.fixture(scope='function')
def mock_statsd_inc(mocker):
    return mocker.patch('app.statsd_client.incr')


@pytest.fixture(scope='function')
def mock_statsd_timing(mocker):
    return mocker.patch('app.statsd_client.timing')


@pytest.fixture(scope='function')
def sample_notification_history(notify_db,
                                notify_db_session,
                                sample_template,
                                status='created',
                                created_at=None):
    if created_at is None:
        created_at = datetime.utcnow()

    notification_history = NotificationHistory(
        id=uuid.uuid4(),
        service=sample_template.service,
        template=sample_template,
        template_version=sample_template.version,
        status=status,
        created_at=created_at,
        notification_type=sample_template.template_type,
        key_type=KEY_TYPE_NORMAL
    )
    notify_db.session.add(notification_history)
    notify_db.session.commit()

    return notification_history


@pytest.fixture(scope='function')
def mock_celery_send_sms_code(mocker):
    return mocker.patch('app.celery.tasks.send_sms_code.apply_async')


@pytest.fixture(scope='function')
def mock_celery_email_registration_verification(mocker):
    return mocker.patch('app.celery.tasks.email_registration_verification.apply_async')


@pytest.fixture(scope='function')
def mock_celery_send_email(mocker):
    return mocker.patch('app.celery.tasks.send_email.apply_async')


@pytest.fixture(scope='function')
def mock_encryption(mocker):
    return mocker.patch('app.encryption.encrypt', return_value="something_encrypted")


@pytest.fixture(scope='function')
def sample_invited_user(notify_db,
                        notify_db_session,
                        service=None,
                        to_email_address=None):

    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if to_email_address is None:
        to_email_address = 'invited_user@digital.gov.uk'

    from_user = service.users[0]

    data = {
        'service': service,
        'email_address': to_email_address,
        'from_user': from_user,
        'permissions': 'send_messages,manage_service,manage_api_keys'
    }
    invited_user = InvitedUser(**data)
    save_invited_user(invited_user)
    return invited_user


@pytest.fixture(scope='function')
def sample_permission(notify_db,
                      notify_db_session,
                      service=None,
                      user=None,
                      permission="manage_settings"):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    data = {
        'user': user,
        'permission': permission
    }
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if service:
        data['service'] = service
    p_model = Permission.query.filter_by(
        user=user,
        service=service,
        permission=permission).first()
    if not p_model:
        p_model = Permission(**data)
        db.session.add(p_model)
        db.session.commit()
    return p_model


@pytest.fixture(scope='function')
def sample_service_permission(notify_db,
                              notify_db_session,
                              service=None,
                              user=None,
                              permission="manage_settings"):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    if service is None:
        service = sample_service(notify_db, notify_db_session, user=user)
    data = {
        'user': user,
        'service': service,
        'permission': permission
    }
    p_model = Permission.query.filter_by(
        user=user,
        service=service,
        permission=permission).first()
    if not p_model:
        p_model = Permission(**data)
        db.session.add(p_model)
        db.session.commit()
    return p_model


@pytest.fixture(scope='function')
def fake_uuid():
    return "6ce466d0-fd6a-11e5-82f5-e0accb9d11a6"


@pytest.fixture(scope='function')
def ses_provider():
    return ProviderDetails.query.filter_by(identifier='ses').one()


@pytest.fixture(scope='function')
def firetext_provider():
    return ProviderDetails.query.filter_by(identifier='mmg').one()


@pytest.fixture(scope='function')
def mmg_provider():
    return ProviderDetails.query.filter_by(identifier='mmg').one()


@pytest.fixture(scope='function')
def sample_provider_statistics(notify_db,
                               notify_db_session,
                               sample_service,
                               provider=None,
                               day=None,
                               unit_count=1):

    if provider is None:
        provider = ProviderDetails.query.filter_by(identifier='mmg').first()
    if day is None:
        day = date.today()
    stats = ProviderStatistics(
        service=sample_service,
        provider_id=provider.id,
        day=day,
        unit_count=unit_count)
    notify_db.session.add(stats)
    notify_db.session.commit()
    return stats


@pytest.fixture(scope='function')
def sample_notification_statistics(notify_db,
                                   notify_db_session,
                                   service=None,
                                   day=None,
                                   emails_requested=2,
                                   emails_delivered=1,
                                   emails_failed=1,
                                   sms_requested=2,
                                   sms_delivered=1,
                                   sms_failed=1):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if day is None:
        day = date.today()
    stats = NotificationStatistics(
        service=service,
        day=day,
        emails_requested=emails_requested,
        emails_delivered=emails_delivered,
        emails_failed=emails_failed,
        sms_requested=sms_requested,
        sms_delivered=sms_delivered,
        sms_failed=sms_failed)
    notify_db.session.add(stats)
    notify_db.session.commit()
    return stats


@pytest.fixture(scope='function')
def mock_firetext_client(mocker, statsd_client=None):
    client = FiretextClient()
    statsd_client = statsd_client or mocker.Mock()
    current_app = mocker.Mock(config={
        'FIRETEXT_API_KEY': 'foo',
        'FROM_NUMBER': 'bar'
    })
    client.init_app(current_app, statsd_client)
    return client


@pytest.fixture(scope='function')
def sms_code_template(notify_db,
                      notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    return create_notify_template(service=service,
                                  user=user,
                                  template_config_name='SMS_CODE_TEMPLATE_ID',
                                  content='((verify_code))',
                                  template_type='sms')


@pytest.fixture(scope='function')
def email_verification_template(notify_db,
                                notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    return create_notify_template(service=service,
                                  user=user,
                                  template_config_name='EMAIL_VERIFY_CODE_TEMPLATE_ID',
                                  content='((user_name)) use ((url)) to complete registration',
                                  template_type='email')


@pytest.fixture(scope='function')
def invitation_email_template(notify_db,
                              notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    content = '((user_name)) is invited to Notify by ((service_name)) ((url)) to complete registration',
    return create_notify_template(service=service,
                                  user=user,
                                  template_config_name='INVITATION_EMAIL_TEMPLATE_ID',
                                  content=content,
                                  subject='Invitation to ((service_name))',
                                  template_type='email')


@pytest.fixture(scope='function')
def password_reset_email_template(notify_db,
                                  notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_notify_template(service=service,
                                  user=user,
                                  template_config_name='PASSWORD_RESET_TEMPLATE_ID',
                                  content='((user_name)) you can reset password by clicking ((url))',
                                  subject='Reset your password',
                                  template_type='email')


@pytest.fixture(scope='function')
def already_registered_template(notify_db,
                                notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    content = """Sign in here: ((signin_url)) If you’ve forgotten your password,
                          you can reset it here: ((forgot_password_url)) feedback:((feedback_url))"""
    return create_notify_template(service=service, user=user,
                                  template_config_name='ALREADY_REGISTERED_EMAIL_TEMPLATE_ID',
                                  content=content,
                                  template_type='email')


@pytest.fixture(scope='function')
def change_email_confirmation_template(notify_db,
                                       notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    content = """Hi ((name)),
              Click this link to confirm your new email address:
              ((url))
              If you didn’t try to change the email address for your GOV.UK Notify account, let us know here:
              ((feedback_url))"""
    template = create_notify_template(service=service,
                                      user=user,
                                      template_config_name='CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID',
                                      content=content,
                                      template_type='email')
    return template


def create_notify_template(service, user, template_config_name, content, template_type, subject=None):
    template = Template.query.get(current_app.config[template_config_name])
    if not template:
        data = {
            'id': current_app.config[template_config_name],
            'name': template_config_name,
            'template_type': template_type,
            'content': content,
            'service': service,
            'created_by': user,
            'subject': subject,
            'archived': False
        }
        template = Template(**data)
        db.session.add(template)
    return template


def notify_service(notify_db, notify_db_session):
    user = sample_user(notify_db, notify_db_session)
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])
    if not service:
        data = {
            'id': current_app.config['NOTIFY_SERVICE_ID'],
            'name': 'Notify Service',
            'message_limit': 1000,
            'active': True,
            'restricted': False,
            'email_from': 'notify.service',
            'created_by': user
        }
        service = Service(**data)
        db.session.add(service)
    return service, user


@pytest.fixture(scope='function')
def sample_service_whitelist(notify_db, notify_db_session, service=None, email_address=None, mobile_number=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)

    if email_address:
        whitelisted_user = ServiceWhitelist.from_string(service.id, EMAIL_TYPE, email_address)
    elif mobile_number:
        whitelisted_user = ServiceWhitelist.from_string(service.id, MOBILE_TYPE, mobile_number)
    else:
        whitelisted_user = ServiceWhitelist.from_string(service.id, EMAIL_TYPE, 'whitelisted_user@digital.gov.uk')

    notify_db.session.add(whitelisted_user)
    notify_db.session.commit()
    return whitelisted_user


@pytest.fixture(scope='function')
def sample_provider_rate(notify_db, notify_db_session, valid_from=None, rate=None, provider_identifier=None):
    create_provider_rates(
        provider_identifier=provider_identifier if provider_identifier is not None else 'mmg',
        valid_from=valid_from if valid_from is not None else datetime.utcnow(),
        rate=rate if rate is not None else 1,
    )
