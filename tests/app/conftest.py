import pytest
from app.models import (User, Service, Template, Token, Job)
from app.dao.users_dao import (save_model_user)
from app.dao.services_dao import save_model_service
from app.dao.templates_dao import save_model_template
from app.dao.tokens_dao import save_model_token
from app.dao.jobs_dao import save_job
import uuid


@pytest.fixture(scope='function')
def sample_user(notify_db,
                notify_db_session,
                email="notify@digital.cabinet-office.gov.uk"):
    user = User(**{'email_address': email})
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
def sample_token(notify_db,
                 notify_db_session,
                 service=None):
    if service is None:
        service = sample_service(notify_db, notify_db_session)
    data = {'service_id': service.id}
    token = Token(**data)
    save_model_token(token)
    return token


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
    data = {
        'id': uuid.uuid4(),
        'service_id': service.id,
        'template_id': template.id,
        'original_file_name': 'some.csv'
    }
    job = Job(**data)
    save_job(job)
    return job
