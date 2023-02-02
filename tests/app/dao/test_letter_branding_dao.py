import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.dao.letter_branding_dao import (
    dao_create_letter_branding,
    dao_get_all_letter_branding,
    dao_get_existing_alternate_letter_branding_for_name,
    dao_get_letter_branding_by_id,
    dao_get_letter_branding_by_name_case_insensitive,
    dao_get_orgs_and_services_associated_with_letter_branding,
    dao_update_letter_branding,
)
from app.models import LetterBranding
from tests.app.db import (
    create_letter_branding,
    create_organisation,
    create_service,
)


def test_dao_get_letter_branding_by_id(notify_db_session):
    letter_branding = create_letter_branding()
    result = dao_get_letter_branding_by_id(letter_branding.id)

    assert result == letter_branding


def test_dao_get_letter_brand_by_id_raises_exception_if_does_not_exist(notify_db_session):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_get_letter_branding_by_id(uuid.uuid4())


def test_dao_get_all_letter_branding(notify_db_session):
    hm_gov = create_letter_branding()
    test_branding = create_letter_branding(
        name="test branding",
        filename="test-branding",
    )

    results = dao_get_all_letter_branding()

    assert hm_gov in results
    assert test_branding in results
    assert len(results) == 2


def test_dao_get_all_letter_branding_returns_empty_list_if_no_brands_exist(notify_db_session):
    assert dao_get_all_letter_branding() == []


def test_dao_create_letter_branding(notify_db_session):
    data = {"name": "test-logo", "filename": "test-logo"}
    assert LetterBranding.query.count() == 0
    dao_create_letter_branding(LetterBranding(**data))

    assert LetterBranding.query.count() == 1

    new_letter_branding = LetterBranding.query.first()
    assert new_letter_branding.name == data["name"]
    assert new_letter_branding.filename == data["name"]


def test_dao_update_letter_branding(notify_db_session):
    create_letter_branding(name="original")
    letter_branding = LetterBranding.query.first()
    assert letter_branding.name == "original"
    dao_update_letter_branding(letter_branding.id, name="new name")
    assert LetterBranding.query.first().name == "new name"


def test_get_letter_branding_by_name_case_insensitive_gets_correct_letter_branding(notify_db_session):
    title_case = create_letter_branding(name="Department Name", filename="1")
    upper_case = create_letter_branding(name="DEPARTMENT NAME", filename="2")
    lower_case = create_letter_branding(name="department name", filename="3")
    # without a space, doesn't match
    create_letter_branding(name="departmentname", filename="4")

    brandings = dao_get_letter_branding_by_name_case_insensitive("dEpArTmEnT nAmE")
    assert len(brandings) == 3
    assert title_case in brandings
    assert upper_case in brandings
    assert lower_case in brandings


def test_dao_get_existing_alternate_letter_branding_for_name(notify_db_session):
    original = create_letter_branding(name="Department Name", filename="1")
    create_letter_branding(name="Department Name (alternate 1)", filename="2")
    create_letter_branding(name="department name (alternate 2)", filename="3")
    create_letter_branding(name="Department Name (alternate 40)", filename="4")

    alt_brandings = dao_get_existing_alternate_letter_branding_for_name("dEpArTmEnT nAmE")

    assert len(alt_brandings) == 3
    assert original not in alt_brandings


def test_dao_get_orgs_and_services_associated_with_letter_branding(notify_db_session):
    letter_branding_1 = create_letter_branding(name="branding 1", filename="logo1.svg")
    letter_branding_2 = create_letter_branding(name="branding 2", filename="logo2.svg")

    org_1 = create_organisation(name="org 1", letter_branding_id=letter_branding_1.id)
    create_organisation(name="org 2", letter_branding_id=letter_branding_2.id)

    service_1 = create_service(service_name="service 1")
    service_2 = create_service(service_name="service 2")
    service_3 = create_service(service_name="service 3")

    service_1.letter_branding = letter_branding_1
    service_2.letter_branding = letter_branding_1
    service_3.letter_branding = letter_branding_2

    orgs_and_services = dao_get_orgs_and_services_associated_with_letter_branding(letter_branding_1.id)

    assert orgs_and_services == {
        "services": [{"name": "service 1", "id": service_1.id}, {"name": "service 2", "id": service_2.id}],
        "organisations": [{"name": "org 1", "id": org_1.id}],
    }
