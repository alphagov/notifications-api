import json
import uuid

import freezegun
import pytest
from sqlalchemy.orm.exc import NoResultFound

from app.errors import InvalidRequest
from app.models import TemplateEmailFile, TemplateEmailFileHistory
from app.template_email_files.rest import dao_create_template_email_files
from tests import create_admin_authorization_header
from tests.app.db import create_template_email_file


@freezegun.freeze_time("2025-01-01 11:09:00.000000")
def test_valid_input_creates_template_email_files_post(client, sample_service, sample_email_template):
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "template_id": str(sample_email_template.id),
        "created_by_id": str(sample_service.users[0].id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()
    response = client.post(
        f"/service/{sample_service.id}/{sample_email_template.id}/template_email_files",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["data"]["filename"] == "example.pdf"
    assert json_resp["data"]["retention_period"] == 90
    assert json_resp["data"]["link_text"] == "click this link!"
    assert json_resp["data"]["validate_users_email"]
    assert json_resp["data"]["template_id"] == str(sample_email_template.id)
    assert json_resp["data"]["template_version"] == int(sample_email_template.version)
    assert json_resp["data"]["created_by_id"] == str(sample_service.users[0].id)
    template_email_file = TemplateEmailFile.query.get(str(json_resp["data"]["id"]))
    assert template_email_file.filename == "example.pdf"
    assert template_email_file.retention_period == 90
    assert template_email_file.link_text == "click this link!"
    assert template_email_file.validate_users_email
    assert template_email_file.template_id == sample_email_template.id
    assert template_email_file.template_version == int(sample_email_template.version)
    assert template_email_file.created_by_id == sample_service.users[0].id
    assert template_email_file.version == 1
    assert str(template_email_file.created_at) == "2025-01-01 11:09:00"


def test_create_fails_if_template_not_email_type(client, sample_service, sample_sms_template):
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()
    with pytest.raises(InvalidRequest):
        client.post(
            f"/service/{sample_service.id}/{sample_sms_template.id}/template_email_files",
            headers=[("Content-Type", "application/json"), auth_header],
            data=data,
        )


def test_create_fails_if_template_does_not_exist(client, sample_service):
    non_existent_template_id = uuid.uuid4()
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()
    with pytest.raises(NoResultFound):
        client.post(
            f"/service/{sample_service.id}/{non_existent_template_id}/template_email_files",
            headers=[("Content-Type", "application/json"), auth_header],
            data=data,
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
                "validate_users_email": "not a boolean!",
            },
            '{"status_code": 400, "errors": [{"error": "ValidationError", "message": "validate_users_email not a boolean! is not of type boolean"}]}',  # noqa: E501
        ),
    ],
)
def test_invalid_input_raises_exception_template_email_files_post(
    client, sample_service, sample_email_template, data, expected_error_message
):
    # default to function-scoped fixture if not set as test parameter
    if "template_id" not in data.keys():
        data["template_id"] = str(sample_email_template.id)
    if "template_version" not in data.keys():
        data["template_version"] = int(sample_email_template.version)
    if "created_by_id" not in data.keys():
        data["created_by_id"] = str(sample_service.users[0].id)
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()
    with pytest.raises(Exception) as e:
        client.post(
            f"/service/{sample_service.id}/{sample_email_template.id}/template_email_files",
            headers=[("Content-Type", "application/json"), auth_header],
            data=data,
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
            {
                "filename": "another example.pdf",
                "link_text": "click for an exciting pdf!",
                "retention_period": 30,
                "validate_users_email": False,
            },
        )
    ],
)
def test_get_all_template_files(client, sample_service, sample_email_template, files):
    file_objects = []
    for file in files:
        file["template_id"] = str(sample_email_template.id)
        file["created_by_id"] = str(sample_service.users[0].id)
        file_objects += [create_template_email_file(**file)]
    auth_header = create_admin_authorization_header()
    response = client.get(
        f"/service/{sample_service.id}/{sample_email_template.id}/template_email_files",
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))

    for i in range(len(json_resp["data"])):
        file_from_response = json_resp["data"][i]
        assert file_from_response["id"] == str(file_objects[i].id)
        assert file_from_response["filename"] == file_objects[i].filename
        assert file_from_response["retention_period"] == file_objects[i].retention_period
        assert file_from_response["link_text"] == file_objects[i].link_text
        assert file_from_response["validate_users_email"] == file_objects[i].validate_users_email
        assert file_from_response["template_id"] == str(file_objects[i].template_id)
        assert file_from_response["version"] == int(file_objects[i].template_version)
        assert file_from_response["created_by_id"] == str(file_objects[i].created_by_id)

def test_get_template_email_file_by_template_version(client, sample_service, sample_email_template):
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "template_id": str(sample_email_template.id),
        "created_by_id": str(sample_service.users[0].id),
    }
    file = create_template_email_file(**data)
    sample_email_template.content = "here's some new content"
    dao_update_template(sample_email_template)
    file.retention_period = 30
    file.validate_users_email = False
    file.link_text = "click this new link"
    dao_update_template_email_files(file)
    sample_email_template.content = "here's some newer content"
    dao_update_template(sample_email_template)
    file.retention_period = 10
    file.validate_users_email = True
    file.link_text = "nevermind click the old link again"
    dao_update_template_email_files(file)
    auth_header = create_admin_authorization_header()
    response = client.get(
        f"/service/{sample_service.id}/{sample_email_template.id}/template_email_files/{file.id}/version/3",
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["data"]["template_version"] == 3
    assert json_resp["data"]["version"] == 2
    assert json_resp["data"]["retention_period"] == 30




def test_get_template_email_files_by_id(client, sample_service, sample_email_template):
    data = {
        "id": "d963f496-b075-4e13-90ae-1f009feddbc6",
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "template_id": str(sample_email_template.id),
        "created_by_id": str(sample_service.users[0].id),
    }
    template_email_files = TemplateEmailFile(**data)
    dao_create_template_email_files(template_email_files)
    auth_header = create_admin_authorization_header()
    response = client.get(
        f"/service/{sample_service.id}/{sample_email_template.id}/template_email_files/d963f496-b075-4e13-90ae-1f009feddbc6",
        headers=[("Content-Type", "application/json"), auth_header],
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["data"]["id"] == "d963f496-b075-4e13-90ae-1f009feddbc6"
    assert json_resp["data"]["filename"] == "example.pdf"
    assert json_resp["data"]["retention_period"] == 90
    assert json_resp["data"]["link_text"] == "click this link!"
    assert json_resp["data"]["validate_users_email"]
    assert json_resp["data"]["template_id"] == str(sample_email_template.id)
    assert json_resp["data"]["template_version"] == int(sample_email_template.version)
    assert json_resp["data"]["created_by_id"] == str(sample_service.users[0].id)


