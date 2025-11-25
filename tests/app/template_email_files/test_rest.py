import uuid

import freezegun
import pytest
from sqlalchemy.orm.exc import NoResultFound

from app.dao.templates_dao import dao_update_template
from app.errors import InvalidRequest
from app.models import TemplateEmailFile, TemplateEmailFileHistory
from tests.app.db import create_template_email_file


@freezegun.freeze_time("2025-01-01 11:09:00.000000")
def test_valid_input_creates_template_email_files_post(sample_service, sample_email_template, admin_request):
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
    }
    response = admin_request.post(
        "template_email_files.create_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        _data=data,
        _expected_status=201,
    )
    assert response["data"]["filename"] == "example.pdf"
    assert response["data"]["retention_period"] == 90
    assert response["data"]["link_text"] == "click this link!"
    assert response["data"]["validate_users_email"]
    assert response["data"]["template_id"] == str(sample_email_template.id)
    assert response["data"]["template_version"] == int(sample_email_template.version)
    assert response["data"]["created_by_id"] == str(sample_service.users[0].id)
    template_email_file = TemplateEmailFile.query.get(str(response["data"]["id"]))
    assert template_email_file.filename == "example.pdf"
    assert template_email_file.retention_period == 90
    assert template_email_file.link_text == "click this link!"
    assert template_email_file.validate_users_email
    assert template_email_file.template_id == sample_email_template.id
    assert template_email_file.template_version == int(sample_email_template.version)
    assert template_email_file.created_by_id == sample_service.users[0].id
    assert template_email_file.version == 1
    assert str(template_email_file.created_at) == "2025-01-01 11:09:00"


def test_create_fails_if_template_not_email_type(sample_service, sample_sms_template, admin_request):
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
    }
    with pytest.raises(InvalidRequest):
        admin_request.post(
            "template_email_files.create_template_email_file",
            service_id=sample_service.id,
            template_id=sample_sms_template.id,
            _data=data,
            _expected_status=400,
        )


def test_create_fails_if_template_does_not_exist(sample_service, admin_request):
    non_existent_template_id = uuid.uuid4()
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
    }
    with pytest.raises(NoResultFound):
        admin_request.post(
            "template_email_files.create_template_email_file",
            service_id=sample_service.id,
            template_id=non_existent_template_id,
            _data=data,
            _expected_status=400,
        )


@pytest.mark.parametrize(
    "data, expected_error_message",
    [
        (
            {
                "id": "d963f496-b075-4e13-90ae-1f009feddbc6",
                "filename": "example.pdf",
                "link_text": "click this link!",
                "retention_period": "not an integer",
                "validate_users_email": True,
            },
            '{"status_code": 400, "errors": [{"error": "ValidationError", "message": "retention_period not an integer is not of type integer"}]}',  # noqa: E501
        ),
        (
            {
                "id": "d963f496-b075-4e13-90ae-1f009feddbc6",
                "filename": "example.pdf",
                "link_text": "click this link!",
                "retention_period": 90,
                "validate_users_email": "this is a string",
            },
            '{"status_code": 400, "errors": [{"error": "ValidationError", "message": "validate_users_email this is a string is not of type boolean"}]}',  # noqa: E501
        ),
    ],
)
def test_invalid_input_raises_exception_template_email_files_post(
    client, sample_service, sample_email_template, data, expected_error_message, admin_request
):
    # default to function-scoped fixture if not set as test parameter
    if "template_id" not in data.keys():
        data["template_id"] = str(sample_email_template.id)
    if "template_version" not in data.keys():
        data["template_version"] = int(sample_email_template.version)
    if "created_by_id" not in data.keys():
        data["created_by_id"] = str(sample_service.users[0].id)
    with pytest.raises(Exception) as e:
        admin_request.post(
            "template_email_files.create_template_email_file",
            service_id=sample_service.id,
            template_id=sample_email_template.id,
            _data=data,
            _expected_status=400,
        )
    assert e.value.message == expected_error_message


@pytest.mark.parametrize(
    "files",
    [
        (
            {
                "filename": "example.pdf",
                "link_text": "example.pdf",
                "retention_period": 90,
                "validate_users_email": True,
            },
        ),
        (
            {
                "filename": "example.pdf",
                "link_text": "example.pdf",
                "retention_period": 90,
                "validate_users_email": True,
            },
            {
                "filename": "another example.pdf",
                "link_text": "click for an exciting pdf!",
                "retention_period": 30,
                "validate_users_email": False,
            },
        ),
    ],
)
def test_get_template_email_files_returns_all_files(sample_service, sample_email_template, files, admin_request):
    file_objects = []
    for file in files:
        file["template_id"] = str(sample_email_template.id)
        file["created_by_id"] = str(sample_service.users[0].id)
        file_objects += [create_template_email_file(**file)]
    response = admin_request.get(
        "template_email_files.get_template_email_files",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        _expected_status=200,
    )

    assert {str(file.id) for file in file_objects} == {file["id"] for file in response["data"]}
    assert {file.filename for file in file_objects} == {file["filename"] for file in response["data"]}
    assert {file.retention_period for file in file_objects} == {file["retention_period"] for file in response["data"]}
    assert {file.link_text for file in file_objects} == {file["link_text"] for file in response["data"]}
    assert {file.validate_users_email for file in file_objects} == {
        file["validate_users_email"] for file in response["data"]
    }
    assert {str(file.template_id) for file in file_objects} == {file["template_id"] for file in response["data"]}
    assert {file.version for file in file_objects} == {file["version"] for file in response["data"]}
    assert {str(file.created_by_id) for file in file_objects} == {file["created_by_id"] for file in response["data"]}

def test_get_template_email_file_by_id_returns_correct_file(sample_template_email_file, sample_service, admin_request):
    response = admin_request.get(
        "template_email_files.get_template_email_file_by_id",
        template_id = sample_template_email_file.template_id,
        template_email_files_id = sample_template_email_file.id,
        service_id=sample_service.id,
        _expected_status=200,
    )
    assert response["data"]["id"] == str(sample_template_email_file.id)
    assert response["data"]["version"] == sample_template_email_file.version
