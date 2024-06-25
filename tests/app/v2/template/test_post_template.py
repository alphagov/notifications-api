import pytest
from flask import json

from app.constants import EMAIL_TYPE, LETTER_TYPE, TEMPLATE_TYPES
from tests import create_service_authorization_header
from tests.app.db import create_template

valid_personalisation = {"personalisation": {"Name": "Jo"}}

valid_post = [
    (
        "Some subject",
        "Some content",
        None,
        "Some subject",
        "Some content",
        ('<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">Some content</p>'),
    ),
    (
        "Some subject",
        "Dear ((Name)), Hello. Yours Truly, The Government.",
        valid_personalisation,
        "Some subject",
        "Dear Jo, Hello. Yours Truly, The Government.",
        (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
            "Dear Jo, Hello. Yours Truly, The Government."
            "</p>"
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
            "Dear Jo, Hello. Yours Truly, The Government."
            "</p>"
        ),
    ),
    (
        "Message for ((Name))",
        "Some content",
        valid_personalisation,
        "Message for Jo",
        "Some content",
        ('<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">Some content</p>'),
    ),
]


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
@pytest.mark.parametrize("subject,content,post_data,expected_subject,expected_content,expected_html", valid_post)
def test_valid_post_template_returns_200(
    api_client_request,
    sample_service,
    tmp_type,
    subject,
    content,
    post_data,
    expected_subject,
    expected_content,
    expected_html,
):
    template = create_template(sample_service, template_type=tmp_type, subject=subject, content=content)

    resp_json = api_client_request.post(
        sample_service.id,
        "v2_template.post_template_preview",
        template_id=template.id,
        _data=post_data,
        _expected_status=200,
    )

    assert resp_json["id"] == str(template.id)

    if tmp_type in {EMAIL_TYPE, LETTER_TYPE}:
        assert expected_subject in resp_json["subject"]

    if tmp_type == EMAIL_TYPE:
        assert resp_json["html"] == expected_html
    else:
        assert resp_json["html"] is None

    assert expected_content in resp_json["body"]


@pytest.mark.parametrize("template_type", (EMAIL_TYPE, LETTER_TYPE))
def test_email_and_letter_templates_not_rendered_into_content(
    api_client_request,
    sample_service,
    template_type,
):
    template = create_template(
        sample_service,
        template_type=template_type,
        subject="Test",
        content=("Hello\n\r\n\r\n\n# This is a heading\n\nParagraph"),
    )

    resp_json = api_client_request.post(
        sample_service.id,
        "v2_template.post_template_preview",
        template_id=template.id,
        _data=None,
        _expected_status=200,
    )

    assert resp_json["body"] == template.content


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_invalid_post_template_returns_400(api_client_request, sample_service, tmp_type):
    template = create_template(
        sample_service, template_type=tmp_type, content="Dear ((Name)), Hello ((Missing)). Yours Truly, The Government."
    )

    resp_json = api_client_request.post(
        sample_service.id,
        "v2_template.post_template_preview",
        template_id=template.id,
        _data=valid_personalisation,
        _expected_status=400,
    )

    assert resp_json["errors"][0]["error"] == "BadRequestError"
    assert "Missing personalisation: Missing" in resp_json["errors"][0]["message"]


def test_post_template_with_non_existent_template_id_returns_404(api_client_request, fake_uuid, sample_service):
    json_response = api_client_request.post(
        sample_service.id,
        "v2_template.post_template_preview",
        template_id=fake_uuid,
        _data=valid_personalisation,
        _expected_status=404,
    )

    assert json_response == {"errors": [{"error": "NoResultFound", "message": "No result found"}], "status_code": 404}


def test_post_template_returns_200_without_personalisation(api_client_request, sample_template):
    api_client_request.post(
        sample_template.service_id,
        "v2_template.post_template_preview",
        template_id=sample_template.id,
        _data=None,
        _expected_status=200,
    )


def test_post_template_returns_200_without_personalisation_and_missing_content_header(client, sample_template):
    response = client.post(
        path=f"/v2/template/{sample_template.id}/preview",
        data=None,
        headers=[create_service_authorization_header(service_id=sample_template.service_id)],
    )
    assert response.status_code == 200


def test_post_template_returns_200_without_personalisation_as_valid_json_and_missing_content_header(
    client, sample_template
):
    response = client.post(
        path=f"/v2/template/{sample_template.id}/preview",
        data=json.dumps(None),
        headers=[create_service_authorization_header(service_id=sample_template.service_id)],
    )
    assert response.status_code == 200


def test_post_template_returns_200_with_valid_json_and_missing_content_header(client, sample_template):
    response = client.post(
        path=f"/v2/template/{sample_template.id}/preview",
        data=json.dumps(valid_personalisation),
        headers=[create_service_authorization_header(service_id=sample_template.service_id)],
    )
    assert response.status_code == 200
