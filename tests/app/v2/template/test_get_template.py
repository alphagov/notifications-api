import pytest

from app.constants import EMAIL_TYPE, LETTER_TYPE, SMS_TYPE, TEMPLATE_TYPES
from app.utils import DATETIME_FORMAT
from tests.app.db import create_letter_contact, create_template

get_template_endpoints_and_kwargs = [
    ("v2_template.get_template_by_id", {}),
    ("v2_template.get_template_version_by_id", {"version": 1}),
]


@pytest.mark.parametrize(
    "tmp_type, expected_name, expected_subject,postage",
    [
        (SMS_TYPE, "sms Template Name", None, None),
        (EMAIL_TYPE, "email Template Name", "Template subject", None),
        (LETTER_TYPE, "letter Template Name", "Template subject", "second"),
    ],
)
@pytest.mark.parametrize("endpoint, extra_kwargs", get_template_endpoints_and_kwargs)
def test_get_template_by_id_returns_200(
    api_client_request, sample_service, tmp_type, expected_name, expected_subject, postage, endpoint, extra_kwargs
):
    letter_contact_block_id = None
    if tmp_type == "letter":
        letter_contact_block = create_letter_contact(sample_service, "Buckingham Palace, London, SW1A 1AA")
        letter_contact_block_id = letter_contact_block.id

    template = create_template(sample_service, template_type=tmp_type, contact_block_id=(letter_contact_block_id))

    json_response = api_client_request.get(
        sample_service.id,
        endpoint,
        template_id=template.id,
        **extra_kwargs,
        _expected_status=200,
    )

    expected_response = {
        "id": "{}".format(template.id),
        "type": "{}".format(template.template_type),
        "created_at": template.created_at.strftime(DATETIME_FORMAT),
        "updated_at": None,
        "version": template.version,
        "created_by": template.created_by.email_address,
        "body": template.content,
        "subject": expected_subject,
        "name": expected_name,
        "personalisation": {},
        "postage": postage,
        "letter_contact_block": letter_contact_block.contact_block if letter_contact_block_id else None,
    }

    assert json_response == expected_response


@pytest.mark.parametrize(
    "tmp_type, expected_name, expected_subject,postage",
    [
        (SMS_TYPE, "sms Template Name", None, None),
        (EMAIL_TYPE, "email Template Name", "Template subject", None),
        (LETTER_TYPE, "letter Template Name", "Template subject", "second"),
    ],
)
def test_get_template_version_by_id_returns_200(
    api_client_request, sample_service, tmp_type, expected_name, expected_subject, postage
):
    letter_contact_block_id = None
    if tmp_type == "letter":
        letter_contact_block = create_letter_contact(sample_service, "Buckingham Palace, London, SW1A 1AA")
        letter_contact_block_id = letter_contact_block.id

    template = create_template(sample_service, template_type=tmp_type, contact_block_id=letter_contact_block_id)

    json_response = api_client_request.get(
        sample_service.id,
        "v2_template.get_template_version_by_id",
        template_id=template.id,
        version=1,
        _expected_status=200,
    )

    expected_response = {
        "id": "{}".format(template.id),
        "type": "{}".format(template.template_type),
        "created_at": template.created_at.strftime(DATETIME_FORMAT),
        "updated_at": None,
        "version": template.version,
        "created_by": template.created_by.email_address,
        "body": template.content,
        "subject": expected_subject,
        "name": expected_name,
        "personalisation": {},
        "postage": postage,
        "letter_contact_block": letter_contact_block.contact_block if letter_contact_block_id else None,
    }

    assert json_response == expected_response


@pytest.mark.parametrize(
    "create_template_args, expected_personalisation",
    [
        (
            {
                "template_type": SMS_TYPE,
                "content": "Hello ((placeholder)) ((conditional??yes))",
            },
            {
                "placeholder": {"required": True},
                "conditional": {"required": True},
            },
        ),
        (
            {
                "template_type": EMAIL_TYPE,
                "subject": "((subject))",
                "content": "((content))",
            },
            {
                "subject": {"required": True},
                "content": {"required": True},
            },
        ),
    ],
)
@pytest.mark.parametrize("endpoint, extra_kwargs", get_template_endpoints_and_kwargs)
def test_get_template_by_id_returns_placeholders(
    api_client_request,
    sample_service,
    endpoint,
    extra_kwargs,
    create_template_args,
    expected_personalisation,
):
    template = create_template(sample_service, **create_template_args)

    json_response = api_client_request.get(
        sample_service.id,
        endpoint,
        template_id=template.id,
        **extra_kwargs,
        _expected_status=200,
    )

    assert json_response["personalisation"] == expected_personalisation


@pytest.mark.parametrize("endpoint, extra_kwargs", get_template_endpoints_and_kwargs)
def test_get_letter_template_by_id_returns_placeholders(
    api_client_request,
    sample_service,
    endpoint,
    extra_kwargs,
):
    contact_block = create_letter_contact(
        service=sample_service,
        contact_block="((contact block))",
    )
    template = create_template(
        sample_service,
        template_type=LETTER_TYPE,
        subject="((letterSubject))",
        content="((letter_content))",
        reply_to=contact_block.id,
    )

    json_response = api_client_request.get(
        sample_service.id,
        endpoint,
        template_id=template.id,
        **extra_kwargs,
        _expected_status=200,
    )

    assert json_response["personalisation"] == {
        "letterSubject": {
            "required": True,
        },
        "letter_content": {
            "required": True,
        },
        "contact block": {
            "required": True,
        },
    }


def test_get_template_with_non_existent_template_id_returns_404(api_client_request, fake_uuid, sample_service):
    json_response = api_client_request.get(
        sample_service.id, "v2_template.get_template_by_id", template_id=fake_uuid, _expected_status=404
    )

    assert json_response == {"errors": [{"error": "NoResultFound", "message": "No result found"}], "status_code": 404}


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_get_template_with_non_existent_version_returns_404(api_client_request, sample_service, tmp_type):
    template = create_template(sample_service, template_type=tmp_type)

    invalid_version = template.version + 1

    json_response = api_client_request.get(
        sample_service.id,
        "v2_template.get_template_version_by_id",
        template_id=template.id,
        version=invalid_version,
        _expected_status=404,
    )

    assert json_response == {"errors": [{"error": "NoResultFound", "message": "No result found"}], "status_code": 404}
