import pytest

from flask import json

from app import DATETIME_FORMAT
from app.models import TEMPLATE_TYPES, EMAIL_TYPE, SMS_TYPE, LETTER_TYPE
from tests import create_authorization_header
from tests.app.db import create_template

valid_version_params = [None, 1]


@pytest.mark.parametrize("tmp_type, expected_name, expected_subject,postage", [
    (SMS_TYPE, 'sms Template Name', None, None),
    (EMAIL_TYPE, 'email Template Name', 'Template subject', None),
    (LETTER_TYPE, 'letter Template Name', 'Template subject', "second")
])
@pytest.mark.parametrize("version", valid_version_params)
def test_get_template_by_id_returns_200(
    client, sample_service, tmp_type, expected_name, expected_subject, version, postage
):
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
        "subject": expected_subject,
        'name': expected_name,
        'personalisation': {},
        'postage': postage,
    }

    assert json_response == expected_response


@pytest.mark.parametrize("create_template_args, expected_personalisation", [
    (
        {
            "template_type": SMS_TYPE,
            "content": "Hello ((placeholder)) ((conditional??yes))",
        },
        {
            "placeholder": {
                "required": True
            },
            "conditional": {
                "required": True
            },
        },
    ),
    (
        {
            "template_type": EMAIL_TYPE,
            "subject": "((subject))",
            "content": "((content))",
        },
        {
            "subject": {
                "required": True
            },
            "content": {
                "required": True
            },
        },
    ),
    (
        {
            "template_type": LETTER_TYPE,
            "subject": "((letterSubject))",
            "content": "((letter_content))",
        },
        {
            "letterSubject": {
                "required": True,
            },
            "letter_content": {
                "required": True,
            },
            "contact block": {
                "required": True,
            },
        },
    )
])
@pytest.mark.parametrize("version", valid_version_params)
def test_get_template_by_id_returns_placeholders(
    client,
    sample_service_custom_letter_contact_block,
    version,
    create_template_args,
    expected_personalisation,
):
    template = create_template(sample_service_custom_letter_contact_block, **create_template_args)
    auth_header = create_authorization_header(service_id=sample_service_custom_letter_contact_block.id)

    version_path = '/version/{}'.format(version) if version else ''

    response = client.get(path='/v2/template/{}{}'.format(template.id, version_path),
                          headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))
    assert json_response['personalisation'] == expected_personalisation


def test_get_template_with_non_existent_template_id_returns_404(client, fake_uuid, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/template/{}'.format(fake_uuid),
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
