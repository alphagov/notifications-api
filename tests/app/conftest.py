import pytest
from app.models import (User, Service, Template, ApiKey, Job)
from app.dao.users_dao import (save_model_user)
from app.dao.services_dao import save_model_service
from app.dao.templates_dao import save_model_template
from app.dao.api_key_dao import save_model_api_key
from app.dao.jobs_dao import save_job
import uuid


@pytest.fixture(scope='function')
def sample_user(notify_db,
                notify_db_session,
                email="notify@digital.cabinet-office.gov.uk"):
    data = {
        'name': 'Test User',
        'email_address': email,
        'password': 'password',
        'mobile_number': '+44 7700 900986',
        'state': 'active'
    }
    user = User(**data)
    save_model_user(user)
    return user


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
        'restricted': False}
    service = Service(**data)
    save_model_service(service)
    return service


@pytest.fixture(scope='function')
def sample_template(notify_db,
                    notify_db_session,
                    template_name="Template Name",
                    template_type="sms",
                    content="This is a template",
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
        'original_file_name': 'some.csv'
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
