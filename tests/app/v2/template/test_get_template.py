import pytest
import uuid

from flask import json

from app import DATETIME_FORMAT
from app.models import EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, TEMPLATE_TYPES
from tests import create_authorization_header
from tests.app.db import create_template

valid_version_params = [None, 1]


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
@pytest.mark.parametrize("version", valid_version_params)
def test_get_email_template_by_id_returns_200(client, sample_service, tmp_type, version):
    template = create_template(sample_service, template_type=tmp_type)
    auth_header = create_authorization_header(service_id=sample_service.id)

    version_path = '/version/{}'.format(version) if version else ''

    response = client.get(path='/v2/template/{}{}'.format(template.id, version_path),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    expected_response = {
        'id': '{}'.format(template.id),
        'type': '{}'.format(template.template_type),
        'created_at': template.created_at.strftime(DATETIME_FORMAT),
        'updated_at': None,
        'version': template.version,
        'created_by': template.created_by.email_address,
        'body': template.content,
        "subject": template.subject if tmp_type == EMAIL_TYPE else None
    }

    assert json_response == expected_response


def test_get_template_with_non_existent_template_id_returns_404(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)

    random_template_id = str(uuid.uuid4())

    response = client.get(path='/v2/template/{}'.format(random_template_id),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 404
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response == {
        "errors": [
            {
                "error": "NoResultFound",
                "message": "No result found"
            }
        ],
        "status_code": 404
    }


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_get_template_with_non_existent_version_returns_404(client, sample_service, tmp_type):
    template = create_template(sample_service, template_type=tmp_type)

    auth_header = create_authorization_header(service_id=sample_service.id)

    invalid_version = template.version + 1

    response = client.get(path='/v2/template/{}/version/{}'.format(template.id, invalid_version),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 404
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response == {
        "errors": [
            {
                "error": "NoResultFound",
                "message": "No result found"
            }
        ],
        "status_code": 404
    }
