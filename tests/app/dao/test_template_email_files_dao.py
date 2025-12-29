import datetime

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import NoResultFound

from app.constants import EMAIL_TYPE
from app.dao.template_email_files_dao import (
    dao_archive_template_email_file,
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


def test_dao_get_template_email_file_by_id(sample_template_email_file, sample_service):
    # additional file for new template, get method shouldn't return this file
    new_template = create_template(service=sample_service, template_type=EMAIL_TYPE, template_name="template_two")
    create_template_email_file(
        new_template.id,
        created_by_id=sample_service.users[0].id,
        filename="file_two.pdf",
        link_text="click this other link",
    )
    template_email_file_fetched = dao_get_template_email_file_by_id(str(sample_template_email_file.id))
    assert template_email_file_fetched.id == sample_template_email_file.id
    assert template_email_file_fetched.filename == sample_template_email_file.filename
    assert template_email_file_fetched.link_text == sample_template_email_file.link_text
    assert template_email_file_fetched.retention_period == sample_template_email_file.retention_period
    assert template_email_file_fetched.validate_users_email == sample_template_email_file.validate_users_email
    assert template_email_file_fetched.template_version == sample_template_email_file.template_version
    assert template_email_file_fetched.created_by_id == sample_template_email_file.created_by_id


def test_dao_get_template_email_file_by_id_returns_none_when_not_found():
    with pytest.raises(NoResultFound):
        dao_get_template_email_file_by_id("2117b6ab-0219-4bfa-aaa4-a3248dafa1a0")


def test_dao_get_template_email_files_by_template_id(sample_template_email_file, sample_email_template, sample_service):
    # should be fetched
    file_two = create_template_email_file(
        filename="example_two",
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
    )
    template_two = create_template(service=sample_service, template_type=EMAIL_TYPE, template_name="other_template")
    # shouldn't be fetched
    create_template_email_file(
        filename="example_three", template_id=template_two.id, created_by_id=template_two.created_by_id
    )

    fetched_file_list = dao_get_template_email_files_by_template_id(str(sample_template_email_file.template_id))

    assert len(fetched_file_list) == 2
    assert fetched_file_list[0].template_id == fetched_file_list[1].template_id
    assert fetched_file_list[1].filename == file_two.filename
    assert fetched_file_list[0].id == sample_template_email_file.id
    assert fetched_file_list[0].filename == sample_template_email_file.filename
    assert fetched_file_list[0].link_text == sample_template_email_file.link_text
    assert fetched_file_list[0].retention_period == sample_template_email_file.retention_period
    assert fetched_file_list[0].validate_users_email == sample_template_email_file.validate_users_email
    assert fetched_file_list[0].template_version == sample_template_email_file.template_version
    assert fetched_file_list[0].created_by_id == sample_template_email_file.created_by_id


def test_dao_get_template_email_files_by_template_id_does_not_return_archived_file(sample_template_email_file):
    sample_template_email_file.archived_at = datetime.datetime.now()
    sample_template_email_file.archived_by_id = sample_template_email_file.created_by_id
    fetched_file_list = dao_get_template_email_files_by_template_id(str(sample_template_email_file.template_id))
    assert not fetched_file_list


def test_dao_get_template_email_files_by_template_id_and_version_does_not_return_archived_file(
    sample_template_email_file,
):
    sample_template_email_file.archived_at = datetime.datetime.now()
    sample_template_email_file.archived_by_id = sample_template_email_file.created_by_id
    dao_update_template_email_file(sample_template_email_file)
    fetched_file_latest = dao_get_template_email_files_by_template_id(
        str(sample_template_email_file.template_id), template_version=3
    )
    assert not fetched_file_latest
    fetched_file_latest = dao_get_template_email_files_by_template_id(str(sample_template_email_file.template_id))
    assert not fetched_file_latest


def test_dao_get_template_email_files_by_template_id_historical(sample_email_template, sample_template_email_file):
    sample_email_template.updated_at = datetime.datetime.utcnow()
    dao_update_template(sample_email_template)
    # sample_email_template.updated_at = datetime.datetime.utcnow()
    # dao_update_template(sample_email_template)
    sample_template_email_file.retention_period = 20
    dao_update_template_email_file(sample_template_email_file)
    assert sample_email_template.version == 4
    template_version_to_get = 2
    template_email_file_fetched = dao_get_template_email_files_by_template_id(
        sample_email_template.id, template_version=template_version_to_get
    )[0]
    assert template_email_file_fetched.id == sample_template_email_file.id
    assert template_email_file_fetched.filename == sample_template_email_file.filename
    assert template_email_file_fetched.link_text == sample_template_email_file.link_text
    assert template_email_file_fetched.retention_period == 90  # we want the initial retention period for historical
    assert template_email_file_fetched.validate_users_email == sample_template_email_file.validate_users_email
    assert template_email_file_fetched.template_version == template_version_to_get
    assert template_email_file_fetched.created_by_id == sample_template_email_file.created_by_id


def test_dao_update_template_email_file(sample_email_template, sample_template_email_file):
    sample_template_email_file.link_text = "click this new link"
    sample_template_email_file.retention_period = 30
    dao_update_template_email_file(sample_template_email_file)
    fetched_template_email_file = TemplateEmailFile.query.get(sample_template_email_file.id)
    fetched_template = Template.query.get(sample_email_template.id)
    assert fetched_template_email_file.version == 2
    assert fetched_template_email_file.template_version == 3
    assert fetched_template_email_file.link_text == "click this new link"
    assert fetched_template_email_file.retention_period == 30
    assert fetched_template.version == 3


@freeze_time("2025-12-30 16:06:04.000000")
def test_dao_archive_template_email_file(sample_email_template, sample_template_email_file):
    dao_archive_template_email_file(
        sample_template_email_file,
        sample_template_email_file.created_by_id,
        template_version=sample_email_template.version + 1,
    )

    fetched_email_file = TemplateEmailFile.query.get(sample_template_email_file.id)
    assert fetched_email_file.version == 2
    assert fetched_email_file.archived_at == datetime.datetime(2025, 12, 30, 16, 6, 4)
    assert fetched_email_file.archived_by_id == sample_template_email_file.created_by_id
    assert fetched_email_file.template_version == sample_email_template.version + 1

    fetched_latest_history = TemplateEmailFile.query.filter_by(id=sample_template_email_file.id, version=2).one()
    assert fetched_latest_history.version == 2
    assert fetched_latest_history.archived_at == datetime.datetime(2025, 12, 30, 16, 6, 4)
    assert fetched_latest_history.archived_by_id == sample_template_email_file.created_by_id
    assert fetched_latest_history.template_version == sample_email_template.version + 1
