import requests_mock
import pytest
import uuid
from datetime import (datetime, date, timedelta)

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
    InvitedUser,
    Permission,
    ProviderStatistics,
    ProviderDetails,
    NotificationStatistics)

from app.dao.users_dao import create_secret_code
from app.dao.api_key_dao import _generate_secret
from app.dao.notifications_dao import dao_create_notification
from app.dao.invited_user_dao import save_invited_user
from app.clients.sms.firetext import FiretextClient
from app.clients.sms.mmg import MMGClient

from tests.app import (
    create_model,
    add_user_to_service,
    create_history_from_model
)


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
                name="Test User",
                email_address="notify@digital.cabinet-office.gov.uk",
                password='password',
                mobile_numnber="+447700900986",
                state='active'):
    usr = User.query.filter_by(email_address=email_address).first()
    if not usr:
        usr = create_model('User', **{
            'name': name,
            'email_address': email_address,
            'password': password,
            'mobile_number': mobile_numnber,
            'state': state
        })
    return usr


def create_code(notify_db, notify_db_session, code_type, usr=None, code=None):
    if code is None:
        code = "12345"
    if usr is None:
        usr = sample_user(notify_db, notify_db_session)
    vcode = create_model('VerifyCode', **{
        'code_type': code_type,
        'expiry_datetime': datetime.utcnow() + timedelta(hours=1),
        'user': usr,
        'code': code
    })
    return vcode, code


@pytest.fixture(scope='function')
def sample_email_code(notify_db, notify_db_session):
    return create_code(
        notify_db,
        notify_db_session,
        'email'
    )[0]


@pytest.fixture(scope='function')
def sample_email_code_plus_code(notify_db, notify_db_session):
    return create_code(
        notify_db,
        notify_db_session,
        'email'
    )


@pytest.fixture(scope='function')
def sample_sms_code(notify_db, notify_db_session):
    return create_code(
        notify_db,
        notify_db_session,
        'sms'
    )[0]


@pytest.fixture(scope='function')
def sample_sms_code_plus_code(notify_db, notify_db_session):
    return create_code(
        notify_db,
        notify_db_session,
        'sms'
    )


@pytest.fixture(scope='function')
def sample_service(notify_db,
                   notify_db_session,
                   service_name="Sample service",
                   user=None,
                   active=False,
                   restricted=False,
                   message_limit=1000,
                   email_from="sample.service",
                   with_history=False,
                   version=1):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    service = Service.query.filter_by(name=service_name).first()
    if not service:
        service = create_model('Service', **{
            'name': service_name,
            'message_limit': message_limit,
            'active': active,
            'restricted': restricted,
            'email_from': email_from,
            'created_by': user,
            'users': [user]
        })
    else:
        if user not in service.users:
            add_user_to_service(service, user)
    if with_history:
        history = service_history(
            notify_db,
            notify_db_session,
            service=service,
            version=1
        )
    return service


@pytest.fixture(scope='function')
def service_history(notify_db,
                    notify_db_session,
                    service=None,
                    version=1):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    history = Service.get_history_model().query.filter_by(id=service.id, version=version).first()
    if not history:
        history = create_history_from_model(service, version=version)
    return history


@pytest.fixture(scope='function')
def sample_service_history(notify_db, notify_db_session):
    return sample_service(notify_db, notify_db_session, with_history=True)


@pytest.fixture(scope='function')
def sample_template(notify_db,
                    notify_db_session,
                    template_name="Template Name",
                    template_type="sms",
                    content="This is a template",
                    archived=False,
                    subject_line='Subject',
                    template_version=1,
                    user=None,
                    service=None,
                    created_by=None,
                    with_history=False):
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
        'archived': archived,
        'version': template_version
    }
    if template_type == 'email':
        data.update({
            'subject': subject_line
        })
    template = create_model('Template', **data)
    if with_history:
        history = template_history(
            notify_db,
            notify_db_session,
            template=template,
            version=template_version
        )
    return template


@pytest.fixture(scope='function')
def template_history(notify_db, notify_db_session, template=None, version=1):
    if template is None:
        template = sample_template(notify_db, notify_db_session)
    history = Template.get_history_model().query.filter_by(id=template.id, version=version).first()
    if not history:
        history = create_history_from_model(template, version=version)
    return history


@pytest.fixture(scope='function')
def sample_template_history(notify_db, notify_db_session):
    return sample_template(
        notify_db,
        notify_db_session,
        with_history=True
    )


@pytest.fixture(scope='function')
def sample_template_with_placeholders(notify_db, notify_db_session):
    return sample_template(notify_db, notify_db_session, content="Hello ((name))")


@pytest.fixture(scope='function')
def sample_template_history_with_placeholders(notify_db, notify_db_session):
    return sample_template(notify_db, notify_db_session, content="Hello ((name))", with_history=True)


@pytest.fixture(scope='function')
def sample_email_template(notify_db, notify_db_session):
    return sample_template(notify_db, notify_db_session, template_type='email')


@pytest.fixture(scope='function')
def sample_email_template_history(notify_db, notify_db_session):
    return sample_template(
        notify_db,
        notify_db_session,
        template_type='email',
        with_history=True)


@pytest.fixture(scope='function')
def sample_email_template_with_placeholders(notify_db, notify_db_session):
    return sample_email_template(
        notify_db,
        notify_db_session,
        content="Hello ((name))",
        subject_line="((name))")


@pytest.fixture(scope='function')
def sample_email_template_history_with_placeholders(notify_db, notify_db_session):
    return sample_template(
        notify_db,
        notify_db_session,
        template_type="email",
        content="Hello ((name))",
        subject_line="((name))",
        with_history=True)


@pytest.fixture(scope='function')
def sample_api_key(notify_db,
                   notify_db_session,
                   service=None,
                   version=1,
                   with_history=True):
    if service is None:
        service = sample_service(notify_db, notify_db_session, with_history=with_history)
    data = {
        'service': service,
        'name': uuid.uuid4(),
        'created_by': service.created_by,
        'secret': _generate_secret()}
    api_key = create_model('ApiKey', **data)
    if with_history:
        history = create_history_from_model(api_key, version=version)
    return api_key


@pytest.fixture(scope='function')
def sample_api_key_history(notify_db, notify_db_session):
    return sample_api_key(notify_db, notify_db_session, with_history=True)


@pytest.fixture(scope='function')
def sample_job(notify_db,
               notify_db_session,
               service=None,
               template=None,
               original_file_name="some.csv",
               notification_count=1,
               created_at=datetime.utcnow(),
               with_history=False):
    if service is None:
        service = sample_service(notify_db, notify_db_session, with_history=with_history)
    if template is None:
        template = sample_template(
            notify_db,
            notify_db_session,
            service=service,
            with_history=with_history)
    data = {
        'id': uuid.uuid4(),
        'service_id': service.id,
        'service': service,
        'template_id': template.id,
        'template_version': template.version,
        'original_file_name': original_file_name,
        'notification_count': notification_count,
        'created_at': created_at,
        'created_by': service.created_by
    }
    job = create_model('Job', **data)
    return job


@pytest.fixture(scope='function')
def sample_job_history(notify_db,
                       notify_db_session,
                       service=None,
                       template=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session, with_history=True)
    if template is None:
        template = sample_template(notify_db, notify_db_session, service=service, with_history=True)
    return sample_job(notify_db, notify_db_session, service=service, template=template)


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
def sample_job_history_with_placeholdered_template(notify_db, notify_db_session):
    return sample_job(
        notify_db,
        notify_db_session,
        template=sample_template_history_with_placeholders(notify_db, notify_db_session)
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
            template_type='email',
            service=service)
    return sample_job(
        notify_db,
        notify_db_session,
        service=service,
        template=template)


@pytest.fixture(scope='function')
def sample_email_job_history(notify_db,
                             notify_db_session,
                             service=None,
                             template=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session, with_history=True)
    if template is None:
        template = sample_template(notify_db, notify_db_session, template_type='email', with_history=True)
    return sample_job(
        notify_db,
        notify_db_session,
        service=service,
        template=template)


@pytest.fixture(scope='function')
def sample_notification(notify_db,
                        notify_db_session,
                        service=None,
                        template=None,
                        job=None,
                        job_row_number=None,
                        to_field=None,
                        status='sending',
                        reference=None,
                        created_at=datetime.utcnow(),
                        provider_name=None,
                        content_char_count=160,
                        dao_create=False):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if template is None:
        template = sample_template(notify_db, notify_db_session, service=service)
    if job is None:
        job = sample_job(notify_db, notify_db_session, service=service, template=template)

    notification_id = uuid.uuid4()

    if provider_name is None:
        provider_name = mmg_provider().identifier if template.template_type == 'sms' else ses_provider().identifier

    if to_field:
        to = to_field
    else:
        to = '+447700900855'

    data = {
        'id': notification_id,
        'to': to,
        'job': job,
        'service_id': service.id,
        'service': service,
        'template': template,
        'template_version': template.version,
        'status': status,
        'reference': reference,
        'created_at': created_at,
        'content_char_count': content_char_count
    }
    if job_row_number:
        data['job_row_number'] = job_row_number

    if dao_create:
        notification = Notification(**data)
        dao_create_notification(notification, template.template_type, provider_name)
    else:
        notification = create_model('Notification', **data)
    return notification


@pytest.fixture(scope='function')
def sample_dao_notification(notify_db, notify_db_session):
    return sample_notification(notify_db, notify_db_session, dao_create=True)


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
def mock_celery_remove_job(mocker):
    return mocker.patch('app.celery.tasks.remove_job.apply_async')


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
    invited_user = create_model('InvitedUser', **data)
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
def mock_mmg_client(mocker, statsd_client=None):
    client = MMGClient()
    statsd_client = statsd_client or mocker.Mock()()
    current_app = mocker.Mock(config={
        'MMG_API_KEY': 'foo',
        'FROM_NUMBER': 'bar'
    })
    client.init_app(current_app, statsd_client)
    return client


@pytest.fixture(scope='function')
def sms_code_template(notify_db,
                      notify_db_session):
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

    template = Template.query.get(current_app.config['SMS_CODE_TEMPLATE_ID'])
    if not template:
        data = {
            'id': current_app.config['SMS_CODE_TEMPLATE_ID'],
            'name': 'Sms code template',
            'template_type': 'sms',
            'content': '((verify_code))',
            'service': service,
            'created_by': user,
            'archived': False
        }
        template = Template(**data)
        db.session.add(template)
    return template
