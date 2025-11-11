import json
import uuid

import freezegun
import pytest
from sqlalchemy.orm.exc import NoResultFound

from app.errors import InvalidRequest
from app.models import TemplateEmailFile, TemplateEmailFileHistory
from app.template_email_files.rest import dao_create_template_email_files
from tests import create_admin_authorization_header


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


