import pytest

from app.dao.organisations_dao import (
    dao_create_organisation, dao_get_organisations, dao_get_organisation_by_id, dao_update_organisation
)
from app.models import Organisation

from tests.app.db import create_organisation


def test_create_organisation(notify_db, notify_db_session):
    organisation = create_organisation()

    assert Organisation.query.count() == 1
    organisation_from_db = Organisation.query.first()
    assert organisation == organisation_from_db


def test_get_organisations_gets_all_organisations(notify_db, notify_db_session):
    create_organisation(name='test_org_1')
    create_organisation(name='test_org_2')

    organisations = dao_get_organisations()

    assert len(organisations) == 2


def test_get_organisation_by_id_gets_correct_organisation(notify_db, notify_db_session):
    organisation = create_organisation()

    organisation_from_db = dao_get_organisation_by_id(organisation.id)

    assert organisation_from_db == organisation


def test_update_organisation(notify_db, notify_db_session):
    updated_name = 'new name'
    organisation = create_organisation()

    organisation_from_db = Organisation.query.first()
    assert organisation.name != updated_name

    organisation.name = updated_name

    dao_update_organisation(organisation)
    organisation_from_db = Organisation.query.first()

    assert organisation_from_db.name == updated_name
