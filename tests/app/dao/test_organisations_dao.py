import pytest

from app.dao.organisations_dao import dao_create_organisation
from app.models import Organisation

from tests.app.db import create_organisation


def test_create_organisation(notify_db, notify_db_session):
    organisation = create_organisation()

    assert Organisation.query.count() == 1
    organisation_from_db = Organisation.query.first()
    assert organisation == organisation_from_db
