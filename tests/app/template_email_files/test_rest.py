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

