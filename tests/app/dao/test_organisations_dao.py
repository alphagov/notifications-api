import pytest
from sqlalchemy.exc import IntegrityError

from app.dao.organisations_dao import (
    dao_create_organisation,
    dao_get_organisations,
    dao_get_organisation_by_id,
    dao_update_organisation,
)
from app.models import Organisation

from tests.app.db import create_organisation


def test_create_organisation(notify_db, notify_db_session):
    organisation = create_organisation()

    assert Organisation.query.count() == 1
    organisation_from_db = Organisation.query.first()
    assert organisation == organisation_from_db


def test_create_organisation_without_name_or_colour_is_valid(notify_db, notify_db_session):
    organisation = create_organisation(name=None, colour=None)

    assert Organisation.query.count() == 1
    organisation_from_db = Organisation.query.first()
    assert organisation == organisation_from_db


def test_create_organisation_without_logo_raises_error(notify_db, notify_db_session):
    with pytest.raises(IntegrityError) as excinfo:
        create_organisation(logo=None)
    assert 'column "logo" violates not-null constraint' in str(excinfo.value)
    assert Organisation.query.count() == 0


def test_get_organisations_gets_all_organisations(notify_db, notify_db_session):
    org_1 = create_organisation(name='test_org_1')
    org_2 = create_organisation(name='test_org_2')

    organisations = dao_get_organisations()

    assert len(organisations) == 2
    assert org_1 == organisations[0]
    assert org_2 == organisations[1]


def test_get_organisation_by_id_gets_correct_organisation(notify_db, notify_db_session):
    organisation = create_organisation()

    organisation_from_db = dao_get_organisation_by_id(organisation.id)

    assert organisation_from_db == organisation


def test_update_organisation(notify_db, notify_db_session):
    updated_name = 'new name'
    organisation = create_organisation()

    organisations_1 = Organisation.query.all()

    assert len(organisations_1) == 1
    assert organisations_1[0].name != updated_name

    dao_update_organisation(organisations_1[0], name=updated_name)

    organisations_2 = Organisation.query.all()

    assert len(organisations_2) == 1
    assert organisations_2[0].name == updated_name
