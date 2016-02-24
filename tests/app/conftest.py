import uuid
import pytest

from app import email_safe
from app.models import (User, Service, Template, ApiKey, Job, Notification)
from app.dao.users_dao import (save_model_user, create_user_code)
from app.dao.utils import create_secret_code
from app.dao.services_dao import dao_create_service
from app.dao.templates_dao import save_model_template
from app.dao.api_key_dao import save_model_api_key
from app.dao.jobs_dao import save_job
from app.dao.notifications_dao import save_notification


@pytest.fixture(scope='function')
def service_factory(notify_db, notify_db_session):
    class ServiceFactory(object):
        def get(self, service_name, user=None, template_type=None):
            if not user:
                user = sample_user(notify_db, notify_db_session)
            service = sample_service(notify_db, notify_db_session, service_name, user)
            if template_type == 'email':
                sample_template(
                    notify_db,
                    notify_db_session,
                    template_type=template_type,
                    subject_line=email_safe(service_name),
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
                email="notify@digital.cabinet-office.gov.uk"):
    data = {
        'name': 'Test User',
        'email_address': email,
        'password': 'password',
        'mobile_number': '+447700900986',
        'state': 'active',
        'permissions': []
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
                   user=None):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    data = {
        'name': service_name,
        'users': [user],
        'limit': 1000,
        'active': False,
        'restricted': False,
        'email_from': email_safe(service_name)
    }
    service = Service.query.filter_by(name=service_name).first()
    if not service:
        service = Service(**data)
        dao_create_service(service, user)
    return service


@pytest.fixture(scope='function')
def sample_template(notify_db,
                    notify_db_session,
                    template_name="Template Name",
                    template_type="sms",
                    content="This is a template",
                    subject_line=None,
                    service=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    sample_api_key(notify_db, notify_db_session, service=service)
    data = {
        'name': template_name,
        'template_type': template_type,
        'content': content,
        'service': service
    }
    if template_type == 'email':
        data.update({
            'subject': subject_line
        })
    template = Template(**data)
    save_model_template(template)
    return template


@pytest.fixture(scope='function')
def sample_email_template(
        notify_db,
        notify_db_session,
        template_name="Email Template Name",
        template_type="email",
        content="This is a template",
        subject_line='Email Subject',
        service=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    sample_api_key(notify_db, notify_db_session, service=service)
    data = {
        'name': template_name,
        'template_type': template_type,
        'content': content,
        'service': service
    }
    if subject_line:
        data.update({
            'subject': subject_line
        })
    template = Template(**data)
    save_model_template(template)
    return template


@pytest.fixture(scope='function')
def sample_api_key(notify_db,
                   notify_db_session,
                   service=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    data = {'service_id': service.id, 'name': uuid.uuid4()}
    api_key = ApiKey(**data)
    save_model_api_key(api_key)
    return api_key


@pytest.fixture(scope='function')
def sample_job(notify_db,
               notify_db_session,
               service=None,
               template=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if template is None:
        template = sample_template(notify_db, notify_db_session,
                                   service=service)
    job_id = uuid.uuid4()
    bucket_name = 'service-{}-notify'.format(service.id)
    file_name = '{}.csv'.format(job_id)
    data = {
        'id': uuid.uuid4(),
        'service_id': service.id,
        'template_id': template.id,
        'bucket_name': bucket_name,
        'file_name': file_name,
        'original_file_name': 'some.csv',
        'notification_count': 1
    }
    job = Job(**data)
    save_job(job)
    return job


@pytest.fixture(scope='function')
def sample_admin_service_id(notify_db, notify_db_session):
    admin_user = sample_user(notify_db, notify_db_session, email="notify_admin@digital.cabinet-office.gov.uk")
    admin_service = sample_service(notify_db, notify_db_session, service_name="Sample Admin Service", user=admin_user)
    data = {'service': admin_service, 'name': 'sample admin key'}
    api_key = ApiKey(**data)
    save_model_api_key(api_key)
    return admin_service.id


@pytest.fixture(scope='function')
def mock_secret_code(mocker):
    def _create():
        return '11111'

    mock_class = mocker.patch('app.dao.utils.create_secret_code', side_effect=_create)
    return mock_class


@pytest.fixture(scope='function')
def sample_notification(notify_db,
                        notify_db_session,
                        service=None,
                        template=None,
                        job=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    if template is None:
        template = sample_template(notify_db, notify_db_session, service=service)
    if job is None:
        job = sample_job(notify_db, notify_db_session, service=service, template=template)

    notificaton_id = uuid.uuid4()
    to = '+44709123456'

    data = {
        'id': notificaton_id,
        'to': to,
        'job': job,
        'service': service,
        'template': template
    }
    notification = Notification(**data)
    save_notification(notification)
    return notification


@pytest.fixture(scope='function')
def mock_celery_send_sms_code(mocker):
    return mocker.patch('app.celery.tasks.send_sms_code.apply_async')


@pytest.fixture(scope='function')
def mock_celery_send_email_code(mocker):
    return mocker.patch('app.celery.tasks.send_email_code.apply_async')


@pytest.fixture(scope='function')
def mock_encryption(mocker):
    return mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
