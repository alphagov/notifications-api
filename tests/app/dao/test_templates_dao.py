from datetime import datetime

import pytest
from freezegun import freeze_time
from sqlalchemy.orm.exc import NoResultFound

from app.dao.templates_dao import (
    dao_create_template,
    dao_get_all_templates_for_service,
    dao_get_template_by_id,
    dao_get_template_by_id_and_service_id,
    dao_get_template_versions,
    dao_redact_template,
    dao_update_template,
)
from app.models import Template, TemplateHistory, TemplateRedacted
from tests.app.db import create_letter_contact, create_template


@pytest.mark.parametrize(
    "template_type, subject",
    [
        ("sms", None),
        ("email", "subject"),
        ("letter", "subject"),
    ],
)
def test_create_template(sample_service, sample_user, template_type, subject):
    data = {
        "name": "Sample Template",
        "template_type": template_type,
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    if template_type == "letter":
        data["postage"] = "second"
    if subject:
        data.update({"subject": subject})
    template = Template(**data)
    dao_create_template(template)

    template = Template.query.one()
    assert template.name == "Sample Template"
    assert template.process_type == "normal"
    assert template.has_unsubscribe_link is False


def test_create_template_creates_redact_entry(sample_service):
    assert TemplateRedacted.query.count() == 0

    template = create_template(sample_service)

    redacted = TemplateRedacted.query.one()
    assert redacted.template_id == template.id
    assert redacted.redact_personalisation is False
    assert redacted.updated_by_id == sample_service.created_by_id


def test_create_template_with_reply_to(sample_service, sample_user):
    letter_contact = create_letter_contact(sample_service, "Edinburgh, ED1 1AA")

    data = {
        "name": "Sample Template",
        "template_type": "letter",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
        "reply_to": letter_contact.id,
        "postage": "second",
    }
    template = Template(**data)
    dao_create_template(template)

    assert dao_get_all_templates_for_service(sample_service.id)[0].reply_to == letter_contact.id


def test_update_template(sample_service, sample_user):
    data = {
        "name": "Sample Template",
        "template_type": "sms",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    template = Template(**data)
    dao_create_template(template)
    created = dao_get_all_templates_for_service(sample_service.id)[0]
    assert created.name == "Sample Template"

    created.name = "new name"
    dao_update_template(created)
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == "new name"


def test_dao_update_template_reply_to_none_to_some(sample_service, sample_user):
    letter_contact = create_letter_contact(sample_service, "Edinburgh, ED1 1AA")

    data = {
        "name": "Sample Template",
        "template_type": "letter",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
        "postage": "second",
    }
    template = Template(**data)
    dao_create_template(template)
    created = Template.query.get(template.id)
    assert created.reply_to is None
    assert created.service_letter_contact_id is None

    created.service_letter_contact_id = letter_contact.id
    dao_update_template(created)

    updated = Template.query.get(template.id)
    assert updated.reply_to == letter_contact.id
    assert updated.version == 2
    assert updated.updated_at

    template_history = TemplateHistory.query.filter_by(id=created.id, version=2).one()
    assert template_history.service_letter_contact_id == letter_contact.id
    assert template_history.updated_at == updated.updated_at


def test_dao_update_template_reply_to_some_to_some(sample_service, sample_user):
    letter_contact = create_letter_contact(sample_service, "Edinburgh, ED1 1AA")
    letter_contact_2 = create_letter_contact(sample_service, "London, N1 1DE")

    data = {
        "name": "Sample Template",
        "template_type": "letter",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
        "service_letter_contact_id": letter_contact.id,
        "postage": "second",
    }
    template = Template(**data)
    dao_create_template(template)
    created = Template.query.get(template.id)
    created.service_letter_contact_id = letter_contact_2.id
    dao_update_template(created)
    updated = Template.query.get(template.id)
    assert updated.reply_to == letter_contact_2.id
    assert updated.version == 2
    assert updated.updated_at

    updated_history = TemplateHistory.query.filter_by(id=created.id, version=2).one()
    assert updated_history.service_letter_contact_id == letter_contact_2.id
    assert updated_history.updated_at == updated_history.updated_at


def test_dao_update_template_reply_to_some_to_none(sample_service, sample_user):
    letter_contact = create_letter_contact(sample_service, "Edinburgh, ED1 1AA")
    data = {
        "name": "Sample Template",
        "template_type": "letter",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
        "service_letter_contact_id": letter_contact.id,
        "postage": "second",
    }
    template = Template(**data)
    dao_create_template(template)
    created = Template.query.get(template.id)

    created.service_letter_contact_id = None
    dao_update_template(created)

    updated = Template.query.get(template.id)
    assert updated.reply_to is None
    assert updated.version == 2
    assert updated.updated_at

    history = TemplateHistory.query.filter_by(id=created.id, version=2).one()
    assert history.service_letter_contact_id is None
    assert history.updated_at == updated.updated_at


def test_redact_template(sample_template):
    redacted = TemplateRedacted.query.one()
    assert redacted.template_id == sample_template.id
    assert redacted.redact_personalisation is False

    time = datetime.now()
    with freeze_time(time):
        dao_redact_template(sample_template, sample_template.created_by_id)

    assert redacted.redact_personalisation is True
    assert redacted.updated_at == time
    assert redacted.updated_by_id == sample_template.created_by_id


def test_get_all_templates_for_service(service_factory):
    service_1 = service_factory.get("service 1")
    service_2 = service_factory.get("service 2")

    assert Template.query.count() == 2
    assert len(dao_get_all_templates_for_service(service_1.id)) == 1
    assert len(dao_get_all_templates_for_service(service_2.id)) == 1

    create_template(
        service=service_1,
        template_name="Sample Template 1",
        template_type="sms",
        content="Template content",
    )
    create_template(
        service=service_1,
        template_name="Sample Template 2",
        template_type="sms",
        content="Template content",
    )
    create_template(
        service=service_2,
        template_name="Sample Template 3",
        template_type="sms",
        content="Template content",
    )

    assert Template.query.count() == 5
    assert len(dao_get_all_templates_for_service(service_1.id)) == 3
    assert len(dao_get_all_templates_for_service(service_2.id)) == 2


def test_get_all_templates_for_service_is_alphabetised(sample_service):
    create_template(
        template_name="Sample Template 1", template_type="sms", content="Template content", service=sample_service
    )
    template_2 = create_template(
        template_name="Sample Template 2", template_type="sms", content="Template content", service=sample_service
    )
    create_template(
        template_name="Sample Template 3", template_type="sms", content="Template content", service=sample_service
    )

    assert Template.query.count() == 3
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == "Sample Template 1"
    assert dao_get_all_templates_for_service(sample_service.id)[1].name == "Sample Template 2"
    assert dao_get_all_templates_for_service(sample_service.id)[2].name == "Sample Template 3"

    template_2.name = "AAAAA Sample Template 2"
    dao_update_template(template_2)
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == "AAAAA Sample Template 2"
    assert dao_get_all_templates_for_service(sample_service.id)[1].name == "Sample Template 1"


def test_get_all_returns_empty_list_if_no_templates(sample_service):
    assert Template.query.count() == 0
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 0


def test_get_all_templates_ignores_archived_templates(sample_service):
    normal_template = create_template(template_name="Normal Template", service=sample_service, archived=False)
    archived_template = create_template(template_name="Archived Template", service=sample_service)
    # sample_template fixture uses dao, which forces archived = False at creation.
    archived_template.archived = True
    dao_update_template(archived_template)

    templates = dao_get_all_templates_for_service(sample_service.id)

    assert len(templates) == 1
    assert templates[0] == normal_template


def test_get_all_templates_ignores_hidden_templates(sample_service):
    normal_template = create_template(template_name="Normal Template", service=sample_service, archived=False)

    create_template(template_name="Hidden Template", hidden=True, service=sample_service)

    templates = dao_get_all_templates_for_service(sample_service.id)

    assert len(templates) == 1
    assert templates[0] == normal_template


def test_get_template_by_id_and_service(sample_service):
    sample_template = create_template(template_name="Test Template", service=sample_service)
    template = dao_get_template_by_id_and_service_id(template_id=sample_template.id, service_id=sample_service.id)
    assert template.id == sample_template.id
    assert template.name == "Test Template"
    assert template.version == sample_template.version
    assert not template.redact_personalisation


def test_get_template_by_id_and_service_returns_none_for_hidden_templates(sample_service):
    sample_template = create_template(template_name="Test Template", hidden=True, service=sample_service)

    with pytest.raises(NoResultFound):
        dao_get_template_by_id_and_service_id(template_id=sample_template.id, service_id=sample_service.id)


def test_get_template_version_returns_none_for_hidden_templates(sample_service):
    sample_template = create_template(template_name="Test Template", hidden=True, service=sample_service)

    with pytest.raises(NoResultFound):
        dao_get_template_by_id_and_service_id(sample_template.id, sample_service.id, "1")


def test_get_template_by_id_and_service_returns_none_if_no_template(sample_service, fake_uuid):
    with pytest.raises(NoResultFound) as e:
        dao_get_template_by_id_and_service_id(template_id=fake_uuid, service_id=sample_service.id)
    assert "No row was found when one was required" in str(e.value)


def test_create_template_creates_a_history_record_with_current_data(sample_service, sample_user):
    assert Template.query.count() == 0
    assert TemplateHistory.query.count() == 0
    data = {
        "name": "Sample Template",
        "template_type": "email",
        "subject": "subject",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    template = Template(**data)
    dao_create_template(template)

    assert Template.query.count() == 1

    template_from_db = Template.query.first()
    template_history = TemplateHistory.query.first()

    assert template_from_db.id == template_history.id
    assert template_from_db.name == template_history.name
    assert template_from_db.version == 1
    assert template_from_db.version == template_history.version
    assert sample_user.id == template_history.created_by_id
    assert template_from_db.created_by.id == template_history.created_by_id


def test_update_template_creates_a_history_record_with_current_data(sample_service, sample_user):
    assert Template.query.count() == 0
    assert TemplateHistory.query.count() == 0
    data = {
        "name": "Sample Template",
        "template_type": "email",
        "subject": "subject",
        "content": "Template content",
        "service": sample_service,
        "created_by": sample_user,
    }
    template = Template(**data)
    dao_create_template(template)

    created = dao_get_all_templates_for_service(sample_service.id)[0]
    assert created.name == "Sample Template"
    assert Template.query.count() == 1
    assert Template.query.first().version == 1
    assert TemplateHistory.query.count() == 1

    created.name = "new name"
    dao_update_template(created)

    assert Template.query.count() == 1
    assert TemplateHistory.query.count() == 2

    template_from_db = Template.query.first()

    assert template_from_db.version == 2

    assert TemplateHistory.query.filter_by(name="Sample Template").one().version == 1
    assert TemplateHistory.query.filter_by(name="new name").one().version == 2


def test_get_template_history_version(sample_user, sample_service, sample_template):
    old_content = sample_template.content
    sample_template.content = "New content"
    dao_update_template(sample_template)
    old_template = dao_get_template_by_id_and_service_id(sample_template.id, sample_service.id, "1")
    assert old_template.content == old_content


def test_can_get_template_then_redacted_returns_right_values(sample_template):
    template = dao_get_template_by_id_and_service_id(
        template_id=sample_template.id, service_id=sample_template.service_id
    )
    assert not template.redact_personalisation
    dao_redact_template(template=template, user_id=sample_template.created_by_id)
    assert template.redact_personalisation


def test_get_template_versions(sample_template):
    original_content = sample_template.content
    sample_template.content = "new version"
    dao_update_template(sample_template)
    versions = dao_get_template_versions(service_id=sample_template.service_id, template_id=sample_template.id)
    assert len(versions) == 2
    versions = sorted(versions, key=lambda x: x.version)
    assert versions[0].content == original_content
    assert versions[1].content == "new version"

    assert versions[0].created_at == versions[1].created_at

    assert versions[0].updated_at is None
    assert versions[1].updated_at is not None

    from app.schemas import template_history_schema

    v = template_history_schema.dump(versions, many=True)
    assert len(v) == 2
    assert {template_history["version"] for template_history in v} == {1, 2}


def test_get_template_versions_is_empty_for_hidden_templates(sample_service):
    sample_template = create_template(template_name="Test Template", hidden=True, service=sample_service)
    versions = dao_get_template_versions(service_id=sample_template.service_id, template_id=sample_template.id)
    assert len(versions) == 0


def test_dao_get_template_service_join_request_approved(service_join_request_approved_template):
    template_id = "4d8ee728-100e-4f0e-8793-5638cfa4ffa4"
    template_type = "email"
    partial_content = "has approved your request to join"

    template = dao_get_template_by_id(template_id=template_id)

    assert str(template.id) == template_id
    assert template.template_type == template_type
    assert partial_content in template.content


@pytest.mark.parametrize(
    "postage",
    ["first", "second", "europe", "rest-of-world", "economy"],
)
def test_create_letter_template_with_various_postage_options(sample_service, sample_user, postage):
    data = {
        "name": f"Letter Template - {postage}",
        "template_type": "letter",
        "subject": "Subject",
        "content": "Content of the letter.",
        "service": sample_service,
        "created_by": sample_user,
        "postage": postage,
    }

    template = Template(**data)
    dao_create_template(template)

    template = Template.query.filter_by(name=f"Letter Template - {postage}").one()
    assert template.template_type == "letter"
    assert template.postage == postage


def test_dao_update_template_postage_creates_history_entry(sample_service, sample_user):
    # Create a letter template with "second" class
    template = Template(
        name="Postage Test Template",
        template_type="letter",
        content="Template content",
        subject="subject",
        service=sample_service,
        created_by=sample_user,
        postage="second",
    )
    dao_create_template(template)

    # Update postage to "economy"
    created = Template.query.get(template.id)
    created.postage = "economy"
    dao_update_template(created)

    updated = Template.query.get(template.id)

    assert updated.postage == "economy"
    assert updated.version == 2
    assert updated.updated_at is not None

    history = TemplateHistory.query.filter_by(id=template.id, version=2).one()
    assert history.postage == "economy"
    assert history.updated_at == updated.updated_at
