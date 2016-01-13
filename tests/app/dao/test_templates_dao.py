import pytest
from app.dao.templates_dao import (
    save_model_template, get_model_templates, delete_model_template)
from tests.app.conftest import sample_template as create_sample_template
from app.models import Template


def test_create_template(notify_api, notify_db, notify_db_session, sample_service):
    assert Template.query.count() == 0
    template_name = 'Sample Template'
    data = {
        'name': template_name,
        'template_type': "sms",
        'content': "Template content",
        'service': sample_service}
    template = Template(**data)
    save_model_template(template)
    assert Template.query.count() == 1
    assert Template.query.first().name == template_name
    assert Template.query.first().id == template.id


def test_get_Templates(notify_api, notify_db, notify_db_session, sample_service):
    sample_template = create_sample_template(notify_db,
                                             notify_db_session,
                                             service=sample_service)
    assert Template.query.count() == 1
    assert len(get_model_templates()) == 1
    template_name = "Another Template"
    sample_template = create_sample_template(notify_db,
                                             notify_db_session,
                                             template_name=template_name,
                                             service=sample_service)
    assert Template.query.count() == 2
    assert len(get_model_templates()) == 2


def test_get_user_Template(notify_api, notify_db, notify_db_session, sample_service):
    assert Template.query.count() == 0
    template_name = "Random Template"
    sample_template = create_sample_template(notify_db,
                                             notify_db_session,
                                             template_name=template_name,
                                             service=sample_service)
    assert get_model_templates(template_id=sample_template.id).name == template_name
    assert Template.query.count() == 1


def test_delete_template(notify_api, notify_db, notify_db_session, sample_template):
    assert Template.query.count() == 1
    delete_model_template(sample_template)
    assert Template.query.count() == 0
