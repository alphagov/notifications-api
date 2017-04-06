import pytest
import uuid

from flask import json

from app.models import SMS_TYPE, TEMPLATE_TYPES
from tests import create_authorization_header
from tests.app.db import create_template

valid_personalisation = {
    'personalisation': {'Name': 'Jo'}
}

valid_post = [
    (
        "Some subject",
        "Some content",
        None,
        "Some subject",
        "Some content"
    ),
    (
        "Some subject",
        "Dear ((Name)), Hello. Yours Truly, The Government.",
        valid_personalisation,
        "Some subject",
        "Dear Jo, Hello. Yours Truly, The Government."
    ),
    (
        "Message for ((Name))",
        "Dear ((Name)), Hello. Yours Truly, The Government.",
        valid_personalisation,
        "Message for Jo",
        "Dear Jo, Hello. Yours Truly, The Government."
    ),
    (
        "Message for ((Name))",
        "Some content",
        valid_personalisation,
        "Message for Jo",
        "Some content"
    ),
]


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
@pytest.mark.parametrize("subject,content,post_data,expected_subject,expected_content", valid_post)
def test_valid_post_template_returns_200(
        client, sample_service, tmp_type, subject, content, post_data, expected_subject, expected_content):
    template = create_template(
        sample_service,
        template_type=tmp_type,
        subject=subject,
        content=content)

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/template/{}/preview'.format(template.id),
        data=json.dumps(post_data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['id'] == str(template.id)
    if tmp_type != SMS_TYPE:
        assert expected_subject in resp_json['subject']
    assert expected_content in resp_json['body']


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_invalid_post_template_returns_400(client, sample_service, tmp_type):
    template = create_template(
        sample_service,
        template_type=tmp_type,
        content='Dear ((Name)), Hello ((Missing)). Yours Truly, The Government.')

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/template/{}/preview'.format(template.id),
        data=json.dumps(valid_personalisation),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['errors'][0]['error'] == 'BadRequestError'
    assert 'Missing personalisation: Missing' in resp_json['errors'][0]['message']


def test_post_template_with_non_existent_template_id_returns_404(client, fake_uuid, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/template/{}/preview'.format(fake_uuid),
        data=json.dumps(valid_personalisation),
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
