import pytest

from flask import json

from app import DATETIME_FORMAT
from tests import create_authorization_header
from tests.app.conftest import sample_template as create_sample_template

EMAIL_TYPE = 'email'
SMS_TYPE = 'sms'
LETTER_TYPE = 'letter'

template_types = [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE]
valid_version_params = [None, 1]


@pytest.mark.parametrize("tmp_type", template_types)
@pytest.mark.parametrize("version", valid_version_params)
def test_get_email_template_by_id_returns_200(client, notify_db, notify_db_session, sample_service, tmp_type, version):
    template = create_sample_template(notify_db, notify_db_session, template_type=tmp_type)
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


def test_get_template_with_invalid_template_id_returns_404(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)

    invalid_template_id = 'some_other_id'

    response = client.get(path='/v2/template/{}'.format(invalid_template_id),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 404
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response == {
        "message": "The requested URL was not found on the server.  "
                   "If you entered the URL manually please check your spelling and try again.",
        "result": "error"
    }


@pytest.mark.parametrize("tmp_type", template_types)
def test_get_template_with_invalid_version_returns_404(client, notify_db, notify_db_session, sample_service, tmp_type):
    template = create_sample_template(
        notify_db, notify_db_session, template_type=tmp_type)

    auth_header = create_authorization_header(service_id=sample_service.id)

    # test with version number beyond latest version
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
