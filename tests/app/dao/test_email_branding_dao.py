from app.dao.email_branding_dao import (
    dao_get_email_branding_by_id,
    dao_get_email_branding_by_name,
    dao_get_email_branding_by_name_case_insensitive,
    dao_get_email_branding_options,
    dao_get_existing_alternate_email_branding_for_name,
    dao_get_orgs_and_services_associated_with_email_branding,
    dao_update_email_branding,
)
from app.models import EmailBranding
from tests.app.db import (
    create_email_branding,
    create_organisation,
    create_service,
)


def test_get_email_branding_options_gets_all_email_branding(notify_db_session):
    email_branding_1 = create_email_branding(name="test_email_branding_1")
    email_branding_2 = create_email_branding(name="test_email_branding_2")

    email_branding = dao_get_email_branding_options()

    assert len(email_branding) == 2
    assert email_branding_1 == email_branding[0]
    assert email_branding_2 == email_branding[1]


def test_get_email_branding_by_id_gets_correct_email_branding(notify_db_session):
    email_branding = create_email_branding()

    email_branding_from_db = dao_get_email_branding_by_id(email_branding.id)

    assert email_branding_from_db == email_branding


def test_get_email_branding_by_name_gets_correct_email_branding(notify_db_session):
    email_branding = create_email_branding(name="Crystal Gems")

    email_branding_from_db = dao_get_email_branding_by_name("Crystal Gems")

    assert email_branding_from_db == email_branding


def test_get_email_branding_by_name_case_insensitive_gets_correct_email_branding(notify_db_session):
    title_case = create_email_branding(name="Department Name")
    upper_case = create_email_branding(name="DEPARTMENT NAME")
    lower_case = create_email_branding(name="department name")
    # without a space, doesn't match
    create_email_branding(name="departmentname")

    brandings = dao_get_email_branding_by_name_case_insensitive("dEpArTmEnT nAmE")
    assert len(brandings) == 3
    assert title_case in brandings
    assert upper_case in brandings
    assert lower_case in brandings


def test_update_email_branding(notify_db_session):
    updated_name = "new name"
    create_email_branding()

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert email_branding[0].name != updated_name

    dao_update_email_branding(email_branding[0], name=updated_name)

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert email_branding[0].name == updated_name


def test_email_branding_has_no_domain(notify_db_session):
    create_email_branding()
    email_branding = EmailBranding.query.all()
    assert not hasattr(email_branding, "domain")


def test_dao_get_existing_alternate_email_branding_for_name(notify_db_session):
    original = create_email_branding(name="Department Name")
    create_email_branding(name="Department Name (alternate 1)")
    create_email_branding(name="department name (alternate 2)")
    create_email_branding(name="Department Name (alternate 40)")

    alt_brandings = dao_get_existing_alternate_email_branding_for_name("dEpArTmEnT nAmE")

    assert len(alt_brandings) == 3
    assert original not in alt_brandings


def test_dao_get_orgs_and_services_associated_with_email_branding(notify_db_session):
    email_branding_1 = create_email_branding(name="branding 1")
    email_branding_2 = create_email_branding(name="branding 2")

    org_1 = create_organisation(name="org 1", email_branding_id=email_branding_1.id)
    create_organisation(name="org 2", email_branding_id=email_branding_2.id)

    service_1 = create_service(service_name="service 1")
    service_2 = create_service(service_name="service 2")
    service_3 = create_service(service_name="service 3")

    service_1.email_branding = email_branding_1
    service_2.email_branding = email_branding_1
    service_3.email_branding = email_branding_2

    orgs_and_services = dao_get_orgs_and_services_associated_with_email_branding(email_branding_1.id)

    assert orgs_and_services == {
        "services": [{"name": "service 1", "id": service_1.id}, {"name": "service 2", "id": service_2.id}],
        "organisations": [{"name": "org 1", "id": org_1.id}],
    }
