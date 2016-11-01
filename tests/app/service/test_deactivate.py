import uuid

import pytest

from app.models import Service
from tests import create_authorization_header
from tests.app.conftest import (
    sample_template as create_template,
    sample_api_key as create_api_key
)


def test_deactivate_only_allows_post(client, sample_service):
    auth_header = create_authorization_header(service_id=str(sample_service.id))
    response = client.get('/service/{}/deactivate'.format(uuid.uuid4()), headers=[auth_header])
    assert response.status_code == 405


def test_deactivate_service_errors_with_bad_service_id(client, sample_service):
    auth_header = create_authorization_header(service_id=str(sample_service.id))
    response = client.post('/service/{}/deactivate'.format(uuid.uuid4()), headers=[auth_header])
    assert response.status_code == 404


def test_deactivating_inactive_service_does_nothing(client, sample_service):
    auth_header = create_authorization_header(service_id=str(sample_service.id))
    sample_service.active = False
    response = client.post('/service/{}/deactivate'.format(sample_service.id), headers=[auth_header])
    assert response.status_code == 204
    assert sample_service.name == 'Sample service'


@pytest.fixture
def deactivated_service(client, notify_db, notify_db_session, sample_service):
    create_template(notify_db, notify_db_session, template_name='a')
    create_template(notify_db, notify_db_session, template_name='b')
    create_api_key(notify_db, notify_db_session)
    create_api_key(notify_db, notify_db_session)

    auth_header = create_authorization_header(service_id=str(sample_service.id))
    response = client.post('/service/{}/deactivate'.format(sample_service.id), headers=[auth_header])
    assert response.status_code == 204
    assert response.data == b''
    return sample_service


def test_deactivating_service_changes_name_and_email(deactivated_service):
    assert deactivated_service.name == '_archived_Sample service'
    assert deactivated_service.email_from == '_archived_sample.service'


def test_deactivating_service_revokes_api_keys(deactivated_service):
    assert deactivated_service.api_keys.count() == 2
    for key in deactivated_service.api_keys:
        assert key.expiry_date is not None
        assert key.version == 2


def test_deactivating_service_archives_templates(deactivated_service):
    assert deactivated_service.templates.count() == 2
    for template in deactivated_service.templates:
        assert template.archived is True
        assert template.version == 2


def test_deactivating_service_creates_history(deactivated_service):
    ServiceHistory = Service.get_history_model()
    history = ServiceHistory.query.filter_by(
        id=deactivated_service.id
    ).order_by(
        ServiceHistory.version.desc()
    ).first()

    assert history.version == 2
    assert history.active is False
