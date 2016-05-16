import pytest
from datetime import (datetime, date)
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
from app.dao.users_dao import (save_model_user, create_user_code, create_secret_code)
from app.dao.services_dao import (dao_create_service, dao_add_user_to_service)
from app.dao.templates_dao import dao_create_template
from app.dao.api_key_dao import save_model_api_key
from app.dao.jobs_dao import dao_create_job
from app.dao.notifications_dao import dao_create_notification
from app.dao.invited_user_dao import save_invited_user
import uuid


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
                   restricted=False,
                   limit=1000,
                   email_from="sample.service"):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    data = {
        'name': service_name,
        'message_limit': limit,
        'active': False,
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
                    content="This is a template",
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
    if template_type == 'email':
        data.update({
            'subject': subject_line
        })
    template = Template(**data)
    dao_create_template(template)
    return template


@pytest.fixture(scope='function')
def sample_template_with_placeholders(notify_db, notify_db_session):
    return sample_template(notify_db, notify_db_session, content="Hello ((name))")


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
        content="Hello ((name))",
        subject_line="((name))")


@pytest.fixture(scope='function')
def sample_api_key(notify_db,
                   notify_db_session,
                   service=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    data = {'service': service, 'name': uuid.uuid4(), 'created_by': service.created_by}
    api_key = ApiKey(**data)
    save_model_api_key(api_key)
    return api_key


@pytest.fixture(scope='function')
def sample_job(notify_db,
               notify_db_session,
               service=None,
               template=None,
               notification_count=1,
               created_at=datetime.utcnow()):
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
        'original_file_name': 'some.csv',
        'notification_count': notification_count,
        'created_at': created_at,
        'created_by': service.created_by
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
        'id': uuid.uuid4(),
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
def mock_secret_code(mocker):
    def _create():
        return '11111'

    mock_class = mocker.patch('app.dao.users_dao.create_secret_code', side_effect=_create)
    return mock_class


@pytest.fixture(scope='function')
def sample_notification(notify_db,
                        notify_db_session,
                        service=None,
                        template=None,
                        job=None,
                        to_field=None,
                        status='sending',
                        reference=None,
                        created_at=datetime.utcnow(),
                        provider_name=None,
                        content_char_count=160,
                        create=True):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if template is None:
        template = sample_template(notify_db, notify_db_session, service=service)
    if job is None:
        job = sample_job(notify_db, notify_db_session, service=service, template=template)

    notification_id = uuid.uuid4()

    if provider_name is None:
        provider = mmg_provider() if template.template_type == 'sms' else ses_provider()

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
    notification = Notification(**data)
    if create:
        dao_create_notification(notification, template.template_type, provider.identifier)
    return notification


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
