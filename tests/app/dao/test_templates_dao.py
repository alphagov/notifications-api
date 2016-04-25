from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError
from app.dao.templates_dao import (
    dao_create_template,
    dao_get_template_by_id_and_service_id,
    dao_get_all_templates_for_service,
    dao_update_template
)
from tests.app.conftest import sample_template as create_sample_template
from app.models import Template
import pytest


def test_create_template(sample_service, sample_user):
    data = {
        'name': 'Sample Template',
        'template_type': "sms",
        'content': "Template content",
        'service': sample_service,
        'created_by': sample_user
    }
    template = Template(**data)
    dao_create_template(template)

    assert Template.query.count() == 1
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 1
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == 'Sample Template'


def test_create_email_template(sample_service, sample_user):
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
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 1
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == 'Sample Template'


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


def test_get_all_templates_for_service_in_created_order(notify_db, notify_db_session, sample_service):
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
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == 'Sample Template 1'
    assert dao_get_all_templates_for_service(sample_service.id)[1].name == 'Sample Template 2'
    assert dao_get_all_templates_for_service(sample_service.id)[2].name == 'Sample Template 3'

    template_2.name = 'Sample Template 2 (updated)'
    dao_update_template(template_2)
    assert dao_get_all_templates_for_service(sample_service.id)[0].name == 'Sample Template 2 (updated)'


def test_get_all_returns_empty_list_if_no_templates(sample_service):
    assert Template.query.count() == 0
    assert len(dao_get_all_templates_for_service(sample_service.id)) == 0


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
    assert Template.get_history_model().query.count() == 0
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
    template_history = Template.get_history_model().query.first()

    assert template_from_db.id == template_history.id
    assert template_from_db.name == template_history.name
    assert template_from_db.version == 1
    assert template_from_db.version == template_history.version
    assert sample_user.id == template_history.created_by_id
    assert template_from_db.created_by.id == template_history.created_by_id


def test_update_template_creates_a_history_record_with_current_data(sample_service, sample_user):
    assert Template.query.count() == 0
    assert Template.get_history_model().query.count() == 0
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
    assert Template.get_history_model().query.count() == 1

    created.name = 'new name'
    dao_update_template(created)

    assert Template.query.count() == 1
    assert Template.get_history_model().query.count() == 2

    template_from_db = Template.query.first()

    assert template_from_db.version == 2

    assert Template.get_history_model().query.filter_by(name='Sample Template').one().version == 1
    assert Template.get_history_model().query.filter_by(name='new name').one().version == 2
