from app.dao.organisation_dao import (
    dao_get_organisations,
    dao_get_organisation_by_id,
    dao_update_organisation,
)
from app.models import Organisation

from tests.app.db import create_organisation


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

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert organisation[0].name != updated_name

    dao_update_organisation(organisation[0], name=updated_name)

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert organisation[0].name == updated_name
