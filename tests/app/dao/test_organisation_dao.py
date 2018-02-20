import pytest
from sqlalchemy.exc import IntegrityError

from app.dao.organisation_dao import (
    dao_get_organisations,
    dao_get_organisation_by_id,
    dao_get_organisation_by_service_id,
    dao_get_organisation_services,
    dao_update_organisation,
    dao_add_service_to_organisation,
    dao_get_invited_organisation_user
)
from app.models import Organisation

from tests.app.db import create_organisation, create_service


def test_get_organisations_gets_all_organisations_alphabetically_with_active_organisations_first(
    notify_db,
    notify_db_session
):
    m_active_org = create_organisation(name='m_active_organisation')
    z_inactive_org = create_organisation(name='z_inactive_organisation', active=False)
    a_inactive_org = create_organisation(name='a_inactive_organisation', active=False)
    z_active_org = create_organisation(name='z_active_organisation')
    a_active_org = create_organisation(name='a_active_organisation')

    organisations = dao_get_organisations()

    assert len(organisations) == 5
    assert organisations[0] == a_active_org
    assert organisations[1] == m_active_org
    assert organisations[2] == z_active_org
    assert organisations[3] == a_inactive_org
    assert organisations[4] == z_inactive_org


def test_get_organisation_by_id_gets_correct_organisation(notify_db, notify_db_session):
    organisation = create_organisation()

    organisation_from_db = dao_get_organisation_by_id(organisation.id)

    assert organisation_from_db == organisation


def test_update_organisation(notify_db, notify_db_session):
    updated_name = 'new name'
    create_organisation()

    organisation = Organisation.query.one()

    assert organisation.name != updated_name

    dao_update_organisation(organisation.id, **{'name': updated_name})

    organisation = Organisation.query.one()

    assert organisation.name == updated_name


def test_add_service_to_organisation(notify_db, notify_db_session, sample_service, sample_organisation):
    assert sample_organisation.services == []

    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    assert len(sample_organisation.services) == 1
    assert sample_organisation.services[0].id == sample_service.id


def test_add_service_to_multiple_organisation_raises_error(
        notify_db, notify_db_session, sample_service, sample_organisation):
    another_org = create_organisation()
    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    with pytest.raises(IntegrityError):
        dao_add_service_to_organisation(sample_service, another_org.id)

    assert len(sample_organisation.services) == 1
    assert sample_organisation.services[0] == sample_service


def test_get_organisation_services(notify_db, notify_db_session, sample_service, sample_organisation):
    another_service = create_service(service_name='service 2')
    another_org = create_organisation()

    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    dao_add_service_to_organisation(another_service, sample_organisation.id)

    org_services = dao_get_organisation_services(sample_organisation.id)
    other_org_services = dao_get_organisation_services(another_org.id)

    assert [sample_service.name, another_service.name] == sorted([s.name for s in org_services])
    assert not other_org_services


def test_get_organisation_by_service_id(notify_db, notify_db_session, sample_service, sample_organisation):
    another_service = create_service(service_name='service 2')
    another_org = create_organisation()

    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    dao_add_service_to_organisation(another_service, another_org.id)

    organisation_1 = dao_get_organisation_by_service_id(sample_service.id)
    organisation_2 = dao_get_organisation_by_service_id(another_service.id)

    assert organisation_1 == sample_organisation
    assert organisation_2 == another_org


def test_dao_get_invited_organisation_user(sample_invited_org_user):
    invited_org_user = dao_get_invited_organisation_user(sample_invited_org_user.id)
    assert invited_org_user == sample_invited_org_user


def test_dao_get_users_for_organisation(sample_organisation, sample_user):
    dao