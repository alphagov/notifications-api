import datetime

from app.constants import EMAIL_TYPE
from app.dao.template_email_files_dao import (
    dao_create_template_email_file,
    dao_get_template_email_file_by_id,
    dao_get_template_email_files_by_template_id,
    dao_update_template_email_file,
)
from app.dao.templates_dao import dao_update_template
from app.models import Template, TemplateEmailFile
from tests.app.db import create_template, create_template_email_file


def test_create_template_email_files_dao(sample_email_template, sample_service):
    data = {
        "id": "d963f496-b075-4e13-90ae-1f009feddbc6",
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "template_id": str(sample_email_template.id),
        "template_version": int(sample_email_template.version),
        "created_by_id": str(sample_service.users[0].id),
    }
    template_email_file = TemplateEmailFile(**data)
    dao_create_template_email_file(template_email_file)
    template_email_file = TemplateEmailFile.query.filter(
        TemplateEmailFile.template_id == str(sample_email_template.id)
    ).one()
    assert str(template_email_file.id) == "d963f496-b075-4e13-90ae-1f009feddbc6"
    assert template_email_file.filename == "example.pdf"
    assert template_email_file.link_text == "click this link!"
    assert template_email_file.retention_period == 90
    assert template_email_file.validate_users_email
    assert template_email_file.version == 1
    assert template_email_file.created_by_id == sample_service.users[0].id

