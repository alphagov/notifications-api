import pytest

from flask import json

from app.models import EMAIL_TYPE, LETTER_TYPE, SMS_TYPE, TEMPLATE_TYPES
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
        "Some content",
        (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
            'Some content'
            '</p>'
        ),
    ),
    (
        "Some subject",
        "Dear ((Name)), Hello. Yours Truly, The Government.",
        valid_personalisation,
        "Some subject",
        "Dear Jo, Hello. Yours Truly, The Government.",
        (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
            'Dear Jo, Hello. Yours Truly, The Government.'
            '</p>'
        ),
    ),
    (
        "Message for ((Name))",
        "Dear ((Name)), Hello. Yours Truly, The Government.",
        valid_personalisation,
        "Message for Jo",
        "Dear Jo, Hello. Yours Truly, The Government.",
        (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
            'Dear Jo, Hello. Yours Truly, The Government.'
            '</p>'
        ),
    ),
    (
        "Message for ((Name))",
        "Some content",
        valid_personalisation,
        "Message for Jo",
        "Some content",
        (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
            'Some content'
            '</p>'
        ),
    ),
]


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
@pytest.mark.parametrize(
    "subject,content,post_data,expected_subject,expected_content,expected_html",
    valid_post
)
def test_valid_post_template_returns_200(
    client,
    sample_service,
    tmp_type,
    subject,
    content,
    post_data,
    expected_subject,
    expected_content,
    expected_html,
):
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

    if tmp_type in {EMAIL_TYPE, LETTER_TYPE}:
        assert expected_subject in resp_json['subject']

    if tmp_type == EMAIL_TYPE:
        assert resp_json['html'] == expected_html
    else:
        assert resp_json['html'] is None

    assert expected_content in resp_json['body']


@pytest.mark.parametrize("template_type", (EMAIL_TYPE, LETTER_TYPE))
def test_email_and_letter_templates_not_rendered_into_content(
    client,
    sample_service,
    template_type,
):
    template = create_template(
        sample_service,
        template_type=template_type,
        subject='Test',
        content=(
            'Hello\n'
            '\r\n'
            '\r\n'
            '\n'
            '# This is a heading\n'
            '\n'
            'Paragraph'
        ),
    )

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/template/{}/preview'.format(template.id),
        data=json.dumps(None),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['body'] == template.content


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


def test_post_template_returns_200_without_personalisation(client, sample_template):
    response = client.post(
        path='/v2/template/{}/preview'.format(sample_template.id),
        data=None,
        headers=[('Content-Type', 'application/json'),
                 create_authorization_header(service_id=sample_template.service_id)]
    )
    assert response.status_code == 200


def test_post_template_returns_200_without_personalisation_and_missing_content_header(client, sample_template):
    response = client.post(
        path='/v2/template/{}/preview'.format(sample_template.id),
        data=None,
        headers=[create_authorization_header(service_id=sample_template.service_id)]
    )
    assert response.status_code == 200


def test_post_template_returns_200_without_personalisation_as_valid_json_and_missing_content_header(
        client, sample_template
):
    response = client.post(
        path='/v2/template/{}/preview'.format(sample_template.id),
        data=json.dumps(None),
        headers=[create_authorization_header(service_id=sample_template.service_id)]
    )
    assert response.status_code == 200


def test_post_template_returns_200_with_valid_json_and_missing_content_header(client, sample_template):
    response = client.post(
        path='/v2/template/{}/preview'.format(sample_template.id),
        data=json.dumps(valid_personalisation),
        headers=[create_authorization_header(service_id=sample_template.service_id)]
    )
    assert response.status_code == 200
