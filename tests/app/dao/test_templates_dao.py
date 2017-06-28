from datetime import datetime

from freezegun import freeze_time
from sqlalchemy.orm.exc import NoResultFound
import pytest

from app.dao.templates_dao import (
    dao_create_template,
    dao_get_template_by_id_and_service_id,
    dao_get_all_templates_for_service,
    dao_update_template,
    dao_get_template_versions,
    dao_get_templates_for_cache,
    dao_redact_template)
from app.models import Template, TemplateHistory, TemplateRedacted

from tests.app.conftest import sample_template as create_sample_template
from tests.app.db import create_template


@pytest.mark.parametrize('template_type, subject', [
    ('sms', None),
    ('email', 'subject'),
    ('letter', 'subject'),
])
def test_create_template(sample_service, sample_user, template_type, subject):
    data = {
        'name': 'Sample Template',
        'template_type': template_type,
        'content': "Template content",
        'service': sample_service,
        'created_by': sample_user
    }
    if subject:
        data.update({'subject': subject})
    template = Template(**data)
    dao_create_template(template)

    assert Template.query.count() == 1
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 1
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == 'Sample Template'
    assert dao_get_all_templates_for_service(sample_service.id)[0].process_type == 'normal'


def test_create_template_creates_redact_entry(sample_service):
    assert TemplateRedacted.query.count() == 0

    template = create_template(sample_service)

    redacted = TemplateRedacted.query.one()
    assert redacted.template_id == template.id
    assert redacted.redact_personalisation is False
    assert redacted.updated_by_id == sample_service.created_by_id


def test_update_template(sample_service, sample_user):
    data = {
        'name': 'Sample Template',
        'template_type': "sms",
        'content': "Template content",
        'service': sample_service,
        'created_by': sample_user
    }
    template = Template(**data)
    dao_create_template(template)
    created = dao_get_all_templates_for_service(sample_service.id)[0]
    assert created.name == 'Sample Template'

    created.name = 'new name'
    dao_update_template(created)
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == 'new name'


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


def test_get_all_templates_for_service(notify_db, notify_db_session, service_factory):
    service_1 = service_factory.get('service 1', email_from='service.1')
    service_2 = service_factory.get('service 2', email_from='service.2')

    assert Template.query.count() == 2
    assert len(dao_get_all_templates_for_service(service_1.id)) == 1
    assert len(dao_get_all_templates_for_service(service_2.id)) == 1

    template_1 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 1',
        template_type="sms",
        content="Template content",
        service=service_1
    )
    template_2 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 2',
        template_type="sms",
        content="Template content",
        service=service_1
    )
    template_3 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 3',
        template_type="sms",
        content="Template content",
        service=service_2
    )

    assert Template.query.count() == 5
    assert len(dao_get_all_templates_for_service(service_1.id)) == 3
    assert len(dao_get_all_templates_for_service(service_2.id)) == 2


def test_get_all_templates_for_service_shows_newest_created_first(notify_db, notify_db_session, sample_service):
    template_1 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 1',
        template_type="sms",
        content="Template content",
        service=sample_service
    )
    template_2 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 2',
        template_type="sms",
        content="Template content",
        service=sample_service
    )
    template_3 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 3',
        template_type="sms",
        content="Template content",
        service=sample_service
    )

    assert Template.query.count() == 3
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == 'Sample Template 3'
    assert dao_get_all_templates_for_service(sample_service.id)[1].name == 'Sample Template 2'
    assert dao_get_all_templates_for_service(sample_service.id)[2].name == 'Sample Template 1'

    template_2.name = 'Sample Template 2 (updated)'
    dao_update_template(template_2)
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == 'Sample Template 3'
    assert dao_get_all_templates_for_service(sample_service.id)[1].name == 'Sample Template 2 (updated)'


def test_get_all_returns_empty_list_if_no_templates(sample_service):
    assert Template.query.count() == 0
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 0


def test_get_all_templates_ignores_archived_templates(notify_db, notify_db_session, sample_service):
    normal_template = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Normal Template',
        service=sample_service,
        archived=False
    )
    archived_template = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Archived Template',
        service=sample_service
    )
    # sample_template fixture uses dao, which forces archived = False at creation.
    archived_template.archived = True
    dao_update_template(archived_template)

    templates = dao_get_all_templates_for_service(sample_service.id)

    assert len(templates) == 1
    assert templates[0] == normal_template


def test_get_template_by_id_and_service(notify_db, notify_db_session, sample_service):
    sample_template = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Test Template',
        service=sample_service)
    assert dao_get_template_by_id_and_service_id(
        template_id=sample_template.id,
        service_id=sample_service.id).name == 'Test Template'
    assert Template.query.count() == 1


def test_get_template_by_id_and_service_returns_none_if_no_template(sample_service, fake_uuid):
    with pytest.raises(NoResultFound) as e:
        dao_get_template_by_id_and_service_id(template_id=fake_uuid, service_id=sample_service.id)
    assert 'No row was found for one' in str(e.value)


def test_create_template_creates_a_history_record_with_current_data(sample_service, sample_user):
    assert Template.query.count() == 0
    assert TemplateHistory.query.count() == 0
    data = {
        'name': 'Sample Template',
        'template_type': "email",
        'subject': "subject",
        'content': "Template content",
        'service': sample_service,
        'created_by': sample_user
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
        'name': 'Sample Template',
        'template_type': "email",
        'subject': "subject",
        'content': "Template content",
        'service': sample_service,
        'created_by': sample_user
    }
    template = Template(**data)
    dao_create_template(template)

    created = dao_get_all_templates_for_service(sample_service.id)[0]
    assert created.name == 'Sample Template'
    assert Template.query.count() == 1
    assert Template.query.first().version == 1
    assert TemplateHistory.query.count() == 1

    created.name = 'new name'
    dao_update_template(created)

    assert Template.query.count() == 1
    assert TemplateHistory.query.count() == 2

    template_from_db = Template.query.first()

    assert template_from_db.version == 2

    assert TemplateHistory.query.filter_by(name='Sample Template').one().version == 1
    assert TemplateHistory.query.filter_by(name='new name').one().version == 2


def test_get_template_history_version(sample_user, sample_service, sample_template):
    old_content = sample_template.content
    sample_template.content = "New content"
    dao_update_template(sample_template)
    old_template = dao_get_template_by_id_and_service_id(
        sample_template.id,
        sample_service.id,
        '1'
    )
    assert old_template.content == old_content


def test_get_template_versions(sample_template):
    original_content = sample_template.content
    sample_template.content = 'new version'
    dao_update_template(sample_template)
    versions = dao_get_template_versions(service_id=sample_template.service_id, template_id=sample_template.id)
    assert len(versions) == 2
    versions = sorted(versions, key=lambda x: x.version)
    assert versions[0].content == original_content
    assert versions[1].content == 'new version'

    assert versions[0].created_at == versions[1].created_at

    assert versions[0].updated_at is None
    assert versions[1].updated_at is not None

    from app.schemas import template_history_schema
    v = template_history_schema.load(versions, many=True)
    assert len(v) == 2


def test_get_templates_by_ids_successful(notify_db, notify_db_session):
    template_1 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 1',
        template_type="sms",
        content="Template content"
    )
    template_2 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 2',
        template_type="sms",
        content="Template content"
    )
    create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 3',
        template_type="email",
        content="Template content"
    )
    sample_cache_dict = {str.encode(str(template_1.id)): str.encode('2'),
                         str.encode(str(template_2.id)): str.encode('3')}
    cache = [[k, v] for k, v in sample_cache_dict.items()]
    templates = dao_get_templates_for_cache(cache)
    assert len(templates) == 2
    assert [(template_1.id, template_1.template_type, template_1.name, 2),
            (template_2.id, template_2.template_type, template_2.name, 3)] == templates


def test_get_templates_by_ids_successful_for_one_cache_item(notify_db, notify_db_session):
    template_1 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 1',
        template_type="sms",
        content="Template content"
    )
    sample_cache_dict = {str.encode(str(template_1.id)): str.encode('2')}
    cache = [[k, v] for k, v in sample_cache_dict.items()]
    templates = dao_get_templates_for_cache(cache)
    assert len(templates) == 1
    assert [(template_1.id, template_1.template_type, template_1.name, 2)] == templates


def test_get_templates_by_ids_returns_empty_list():
        assert dao_get_templates_for_cache({}) == []
        assert dao_get_templates_for_cache(None) == []
