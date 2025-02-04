import datetime
import uuid

import pytest
from flask import current_app
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db
from app.dao.annual_billing_dao import set_default_free_allowance_for_service
from app.dao.organisation_dao import (
    dao_add_email_branding_list_to_organisation_pool,
    dao_add_email_branding_to_organisation_pool,
    dao_add_letter_branding_list_to_organisation_pool,
    dao_add_service_to_organisation,
    dao_add_user_to_organisation,
    dao_archive_organisation,
    dao_get_email_branding_pool_for_organisation,
    dao_get_letter_branding_pool_for_organisation,
    dao_get_organisation_by_email_address,
    dao_get_organisation_by_id,
    dao_get_organisation_by_service_id,
    dao_get_organisation_live_services_and_their_free_allowance,
    dao_get_organisation_services,
    dao_get_organisations,
    dao_get_users_for_organisation,
    dao_remove_email_branding_from_organisation_pool,
    dao_remove_letter_branding_from_organisation_pool,
    dao_update_organisation,
)
from app.errors import InvalidRequest
from app.models import AnnualBilling, Organisation, Service
from tests.app.db import (
    create_annual_billing,
    create_domain,
    create_email_branding,
    create_letter_branding,
    create_organisation,
    create_service,
    create_user,
)


def test_get_organisations_gets_all_organisations_alphabetically_with_active_organisations_first(notify_db_session):
    m_active_org = create_organisation(name="m_active_organisation")
    z_inactive_org = create_organisation(name="z_inactive_organisation", active=False)
    a_inactive_org = create_organisation(name="a_inactive_organisation", active=False)
    z_active_org = create_organisation(name="z_active_organisation")
    a_active_org = create_organisation(name="a_active_organisation")

    organisations = dao_get_organisations()

    assert len(organisations) == 5
    assert organisations[0] == a_active_org
    assert organisations[1] == m_active_org
    assert organisations[2] == z_active_org
    assert organisations[3] == a_inactive_org
    assert organisations[4] == z_inactive_org


def test_get_organisation_by_id_gets_correct_organisation(notify_db_session):
    organisation = create_organisation()

    organisation_from_db = dao_get_organisation_by_id(organisation.id)

    assert organisation_from_db == organisation


def test_update_organisation(notify_db_session):
    create_organisation()

    organisation = Organisation.query.one()
    user = create_user()
    email_branding = create_email_branding()
    letter_branding = create_letter_branding()

    data = {
        "name": "new name",
        "crown": True,
        "organisation_type": "local",
        "agreement_signed": True,
        "agreement_signed_at": datetime.datetime.utcnow(),
        "agreement_signed_by_id": user.id,
        "agreement_signed_version": 999.99,
        "letter_branding_id": letter_branding.id,
        "email_branding_id": email_branding.id,
    }

    for attribute, value in data.items():
        assert getattr(organisation, attribute) != value

    assert organisation.updated_at is None

    dao_update_organisation(organisation.id, **data)

    organisation = Organisation.query.one()

    for attribute, value in data.items():
        assert getattr(organisation, attribute) == value

    assert organisation.updated_at


@pytest.mark.parametrize(
    "domain_list, expected_domains",
    (
        (["abc", "def"], {"abc", "def"}),
        (["ABC", "DEF"], {"abc", "def"}),
        ([], set()),
        (None, {"123", "456"}),
        pytest.param(["abc", "ABC"], {"abc"}, marks=pytest.mark.xfail(raises=IntegrityError)),
    ),
)
def test_update_organisation_domains_lowercases(
    notify_db_session,
    domain_list,
    expected_domains,
):
    create_organisation()

    organisation = Organisation.query.one()

    # Seed some domains
    dao_update_organisation(organisation.id, domains=["123", "456"])

    # This should overwrite the seeded domains
    dao_update_organisation(organisation.id, domains=domain_list)

    assert {domain.domain for domain in organisation.domains} == expected_domains


def test_update_organisation_does_not_update_the_service_if_certain_attributes_not_provided(
    sample_service,
    sample_organisation,
):
    email_branding = create_email_branding()
    letter_branding = create_letter_branding()

    sample_service.organisation_type = "local"
    sample_organisation.organisation_type = "central"
    sample_organisation.email_branding = email_branding
    sample_organisation.letter_branding = letter_branding

    sample_organisation.services.append(sample_service)
    db.session.commit()

    assert sample_organisation.name == "sample organisation"

    dao_update_organisation(sample_organisation.id, name="updated org name")

    assert sample_organisation.name == "updated org name"

    assert sample_organisation.organisation_type == "central"
    assert sample_service.organisation_type == "local"

    assert sample_organisation.email_branding == email_branding
    assert sample_service.email_branding is None

    assert sample_organisation.letter_branding == letter_branding
    assert sample_service.letter_branding is None


def test_update_organisation_updates_the_service_org_type_if_org_type_is_provided(
    sample_service,
    sample_organisation,
):
    sample_service.organisation_type = "local"
    sample_organisation.organisation_type = "local"
    set_default_free_allowance_for_service(service=sample_service, year_start=None)
    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1
    assert annual_billing[0].service_id == sample_service.id
    assert annual_billing[0].free_sms_fragment_limit == 10000

    sample_organisation.services.append(sample_service)
    db.session.commit()

    dao_update_organisation(sample_organisation.id, organisation_type="central")

    assert sample_organisation.organisation_type == "central"
    assert sample_service.organisation_type == "central"
    assert (
        Service.get_history_model().query.filter_by(id=sample_service.id, version=2).one().organisation_type
        == "central"
    )
    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1
    assert annual_billing[0].service_id == sample_service.id
    assert annual_billing[0].free_sms_fragment_limit == 30000


def test_update_organisation_updates_the_service_branding_if_branding_is_provided(
    sample_service,
    sample_organisation,
):
    email_branding = create_email_branding()
    letter_branding = create_letter_branding()

    sample_organisation.services.append(sample_service)
    db.session.commit()

    dao_update_organisation(sample_organisation.id, email_branding_id=email_branding.id)
    dao_update_organisation(sample_organisation.id, letter_branding_id=letter_branding.id)

    assert sample_organisation.email_branding == email_branding
    assert sample_organisation.letter_branding == letter_branding
    assert sample_service.email_branding == email_branding
    assert sample_service.letter_branding == letter_branding


def test_update_organisation_does_not_override_service_branding(
    sample_service,
    sample_organisation,
):
    email_branding = create_email_branding()
    custom_email_branding = create_email_branding(name="custom")
    letter_branding = create_letter_branding()
    custom_letter_branding = create_letter_branding(name="custom", filename="custom")

    sample_service.email_branding = custom_email_branding
    sample_service.letter_branding = custom_letter_branding

    sample_organisation.services.append(sample_service)
    db.session.commit()

    dao_update_organisation(sample_organisation.id, email_branding_id=email_branding.id)
    dao_update_organisation(sample_organisation.id, letter_branding_id=letter_branding.id)

    assert sample_organisation.email_branding == email_branding
    assert sample_organisation.letter_branding == letter_branding
    assert sample_service.email_branding == custom_email_branding
    assert sample_service.letter_branding == custom_letter_branding


def test_update_organisation_email_branding_adds_to_pool(sample_organisation):
    email_branding = create_email_branding()
    db.session.commit()

    assert email_branding not in sample_organisation.email_branding_pool

    dao_update_organisation(sample_organisation.id, email_branding_id=email_branding.id)

    assert email_branding in sample_organisation.email_branding_pool


@pytest.mark.parametrize("email_branding_id_present", (True, False))
def test_update_organisation_email_branding_adds_nhs_branding_to_pool(
    sample_organisation,
    nhs_email_branding,
    nhs_letter_branding,
    email_branding_id_present,
):
    email_branding_id = current_app.config["NHS_EMAIL_BRANDING_ID"] if email_branding_id_present else None

    data = {
        "organisation_type": "nhs_central",
        "email_branding_id": email_branding_id,
    }

    assert not sample_organisation.email_branding_pool

    dao_update_organisation(sample_organisation.id, **data)

    assert len(sample_organisation.email_branding_pool) == 1
    assert sample_organisation.email_branding_pool[0].id == nhs_email_branding.id


def test_update_organisation_email_branding_does_not_error_if_already_in_pool(sample_organisation):
    email_branding = create_email_branding()
    sample_organisation.email_branding_pool.append(email_branding)
    db.session.commit()

    assert email_branding in sample_organisation.email_branding_pool

    dao_update_organisation(sample_organisation.id, email_branding_id=email_branding.id)


def test_update_organisation_email_branding_does_not_error_if_returning_to_govuk_brand(sample_organisation):
    dao_update_organisation(sample_organisation.id, email_branding_id=None)


def test_update_organisation_letter_branding_adds_to_pool(sample_organisation):
    letter_branding = create_letter_branding()

    assert letter_branding not in sample_organisation.letter_branding_pool

    dao_update_organisation(sample_organisation.id, letter_branding_id=letter_branding.id)

    assert letter_branding in sample_organisation.letter_branding_pool


@pytest.mark.parametrize("letter_branding_id_present", (True, False))
def test_update_organisation_letter_branding_adds_nhs_branding_to_pool(
    sample_organisation,
    nhs_email_branding,
    nhs_letter_branding,
    letter_branding_id_present,
):
    letter_branding_id = current_app.config["NHS_LETTER_BRANDING_ID"] if letter_branding_id_present else None

    data = {
        "organisation_type": "nhs_central",
        "letter_branding_id": letter_branding_id,
    }

    assert not sample_organisation.letter_branding_pool

    dao_update_organisation(sample_organisation.id, **data)

    assert len(sample_organisation.letter_branding_pool) == 1
    assert sample_organisation.letter_branding_pool[0].id == nhs_letter_branding.id


def test_update_organisation_letter_branding_does_not_error_if_already_in_pool(sample_organisation):
    letter_branding = create_letter_branding()
    sample_organisation.letter_branding_pool.append(letter_branding)
    db.session.commit()

    assert letter_branding in sample_organisation.letter_branding_pool

    dao_update_organisation(sample_organisation.id, letter_branding_id=letter_branding.id)


def test_update_organisation_letter_branding_does_not_error_if_returning_to_no_branding(sample_organisation):
    dao_update_organisation(sample_organisation.id, letter_branding_id=None)


def test_update_organisation_updates_services_with_new_crown_type(sample_service, sample_organisation):
    sample_organisation.services.append(sample_service)
    db.session.commit()

    assert Service.query.get(sample_service.id).crown

    dao_update_organisation(sample_organisation.id, crown=False)

    assert not Service.query.get(sample_service.id).crown


@freeze_time("2022-05-17 11:09:16")
def test_dao_archive_organisation(sample_organisation, fake_uuid):
    email_branding = create_email_branding(id=fake_uuid)
    letter_branding = create_letter_branding()

    dao_update_organisation(
        sample_organisation.id,
        domains=["example.com", "test.com"],
        email_branding_id=email_branding.id,
        letter_branding_id=letter_branding.id,
    )

    org_name = sample_organisation.name

    dao_archive_organisation(sample_organisation.id)

    assert not sample_organisation.email_branding
    assert not sample_organisation.letter_branding
    assert not sample_organisation.domains
    assert sample_organisation.active is False
    assert sample_organisation.name == f"_archived_2022-05-17-11:09:16_{org_name}"


def test_add_service_to_organisation(sample_service, sample_organisation):
    assert sample_organisation.services == []

    sample_service.organisation_type = "central"
    sample_organisation.organisation_type = "local"
    sample_organisation.crown = False

    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    assert len(sample_organisation.services) == 1
    assert sample_organisation.services[0].id == sample_service.id

    assert sample_service.organisation_type == sample_organisation.organisation_type
    assert sample_service.crown == sample_organisation.crown
    assert (
        Service.get_history_model().query.filter_by(id=sample_service.id, version=2).one().organisation_type
        == sample_organisation.organisation_type
    )
    assert sample_service.organisation_id == sample_organisation.id


def test_get_organisation_services(sample_service, sample_organisation):
    another_service = create_service(service_name="service 2")
    another_org = create_organisation()

    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    dao_add_service_to_organisation(another_service, sample_organisation.id)

    org_services = dao_get_organisation_services(sample_organisation.id)
    other_org_services = dao_get_organisation_services(another_org.id)

    assert [sample_service.name, another_service.name] == sorted([s.name for s in org_services])
    assert not other_org_services


def test_get_organisation_by_service_id(sample_service, sample_organisation):
    another_service = create_service(service_name="service 2")
    another_org = create_organisation()

    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    dao_add_service_to_organisation(another_service, another_org.id)

    organisation_1 = dao_get_organisation_by_service_id(sample_service.id)
    organisation_2 = dao_get_organisation_by_service_id(another_service.id)

    assert organisation_1 == sample_organisation
    assert organisation_2 == another_org


def test_dao_get_users_for_organisation(sample_organisation):
    first = create_user(email="first@invited.com")
    second = create_user(email="another@invited.com")

    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=first.id, permissions=[])
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=second.id, permissions=[])

    results = dao_get_users_for_organisation(organisation_id=sample_organisation.id)

    assert len(results) == 2
    assert results[0] == first
    assert results[1] == second


def test_dao_get_users_for_organisation_returns_empty_list(sample_organisation):
    results = dao_get_users_for_organisation(organisation_id=sample_organisation.id)
    assert len(results) == 0


def test_dao_get_users_for_organisation_only_returns_active_users(sample_organisation):
    first = create_user(email="first@invited.com")
    second = create_user(email="another@invited.com")

    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=first.id, permissions=[])
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=second.id, permissions=[])

    second.state = "inactive"

    results = dao_get_users_for_organisation(organisation_id=sample_organisation.id)
    assert len(results) == 1
    assert results[0] == first


@pytest.mark.parametrize("permissions", ([], ["can_make_services_live"]))
def test_add_user_to_organisation_returns_user(sample_organisation, permissions):
    org_user = create_user()
    assert not org_user.organisations

    added_user = dao_add_user_to_organisation(
        organisation_id=sample_organisation.id,
        user_id=org_user.id,
        permissions=permissions,
    )
    assert len(added_user.organisations) == 1
    assert added_user.organisations[0] == sample_organisation
    assert added_user.get_organisation_permissions()[str(sample_organisation.id)] == permissions


def test_add_user_to_organisation_when_user_does_not_exist(sample_organisation):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=uuid.uuid4(), permissions=[])


def test_add_user_to_organisation_when_organisation_does_not_exist(sample_user):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_add_user_to_organisation(organisation_id=uuid.uuid4(), user_id=sample_user.id, permissions=[])


@pytest.mark.parametrize(
    "domain, expected_org",
    (
        ("unknown.gov.uk", False),
        ("example.gov.uk", True),
    ),
)
def test_get_organisation_by_email_address(domain, expected_org, notify_db_session):
    org = create_organisation()
    create_domain("example.gov.uk", org.id)
    create_domain("test.gov.uk", org.id)

    another_org = create_organisation(name="Another")
    create_domain("cabinet-office.gov.uk", another_org.id)
    create_domain("cabinetoffice.gov.uk", another_org.id)

    found_org = dao_get_organisation_by_email_address(f"test@{domain}")

    if expected_org:
        assert found_org is org
    else:
        assert found_org is None


def test_get_organisation_by_email_address_ignores_gsi_gov_uk(notify_db_session):
    org = create_organisation()
    create_domain("example.gov.uk", org.id)

    found_org = dao_get_organisation_by_email_address("test_gsi_address@example.gsi.gov.uk")
    assert org == found_org


def test_add_to_and_get_email_branding_pool_for_organisation(sample_organisation):
    first_branding = create_email_branding(colour="blue", logo="test_x1.png", name="email_branding_1")
    second_branding = create_email_branding(colour="indigo", logo="test_x2.png", name="email_branding_2")
    third_branding = create_email_branding(colour="indigo", logo="test_x3.png", name="email_branding_3")

    organisation_1 = sample_organisation
    organisation_2 = create_organisation()

    dao_add_email_branding_to_organisation_pool(organisation_id=organisation_1.id, email_branding_id=first_branding.id)
    dao_add_email_branding_to_organisation_pool(organisation_id=organisation_1.id, email_branding_id=second_branding.id)
    dao_add_email_branding_to_organisation_pool(organisation_id=organisation_2.id, email_branding_id=third_branding.id)

    results = dao_get_email_branding_pool_for_organisation(organisation_id=organisation_1.id)

    assert len(results) == 2
    assert results[0] == first_branding
    assert results[1] == second_branding
    # We test to ensure that branding that belongs to \
    # another Organisation's email branding pool is not returned
    assert third_branding not in results


def test_dao_add_email_branding_list_to_organisation_pool(sample_organisation):
    branding_1 = create_email_branding(logo="test_x1.png", name="branding_1")
    branding_2 = create_email_branding(logo="test_x2.png", name="branding_2")
    branding_3 = create_email_branding(logo="test_x3.png", name="branding_3")

    dao_add_email_branding_list_to_organisation_pool(sample_organisation.id, [branding_1.id])

    assert sample_organisation.email_branding_pool == [branding_1]

    dao_add_email_branding_list_to_organisation_pool(sample_organisation.id, [branding_2.id, branding_3.id])

    # existing brandings remain in the pool, while new ones get added
    assert len(sample_organisation.email_branding_pool) == 3
    assert branding_1 in sample_organisation.email_branding_pool
    assert branding_2 in sample_organisation.email_branding_pool
    assert branding_3 in sample_organisation.email_branding_pool


def test_dao_get_organisation_live_services_with_free_allowance(sample_service, sample_organisation):
    service_with_no_free_allowance = create_service(service_name="service 2")

    create_annual_billing(sample_service.id, free_sms_fragment_limit=10, financial_year_start=2015)
    create_annual_billing(sample_service.id, free_sms_fragment_limit=20, financial_year_start=2016)

    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    dao_add_service_to_organisation(service_with_no_free_allowance, sample_organisation.id)

    org_services = (
        dao_get_organisation_live_services_and_their_free_allowance(sample_organisation.id, 2015)
        .order_by(Service.name)
        .all()
    )

    assert len(org_services) == 2

    assert org_services[0].id == sample_service.id
    assert org_services[0].free_sms_fragment_limit == 10

    assert org_services[1].id == service_with_no_free_allowance.id
    assert org_services[1].free_sms_fragment_limit == 0


def test_dao_remove_email_branding_from_organisation_pool(sample_organisation):
    branding_1 = create_email_branding(logo="test_x1.png", name="branding_1")
    branding_2 = create_email_branding(logo="test_x2.png", name="branding_2")
    branding_3 = create_email_branding(logo="test_x3.png", name="branding_3")

    sample_organisation.email_branding_id = branding_2.id
    sample_organisation.email_branding_pool += [branding_1, branding_2, branding_3]

    assert sample_organisation.email_branding_pool == [branding_1, branding_2, branding_3]

    dao_remove_email_branding_from_organisation_pool(sample_organisation.id, branding_1.id)
    assert sample_organisation.email_branding_pool == [branding_2, branding_3]

    # Error if trying to remove an email branding that's not in the pool
    with pytest.raises(ValueError):
        dao_remove_email_branding_from_organisation_pool(sample_organisation.id, branding_1.id)
    assert sample_organisation.email_branding_pool == [branding_2, branding_3]

    # Error if trying to remove the org's default email branding
    with pytest.raises(InvalidRequest):
        dao_remove_email_branding_from_organisation_pool(sample_organisation.id, branding_2.id)
    assert sample_organisation.email_branding_pool == [branding_2, branding_3]

    dao_remove_email_branding_from_organisation_pool(sample_organisation.id, branding_3.id)
    assert sample_organisation.email_branding_pool == [branding_2]


def test_dao_get_letter_branding_pool_for_organisation(sample_organisation):
    branding_1 = create_letter_branding("nhs", "nhs.svg")
    branding_2 = create_letter_branding("cabinet_office", "cabinet_office.svg")

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding_1.id, branding_2.id])

    assert dao_get_letter_branding_pool_for_organisation(sample_organisation.id) == [
        branding_2,
        branding_1,
    ]


def test_dao_add_letter_branding_list_to_organisation_pool(sample_organisation):
    branding_1 = create_letter_branding("branding_1", "filename_1")
    branding_2 = create_letter_branding("branding_2", "filename_2")
    branding_3 = create_letter_branding("branding_3", "filename_3")

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding_1.id])

    assert sample_organisation.letter_branding_pool == [branding_1]

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding_2.id, branding_3.id])

    # existing brandings remain in the pool, while new ones get added
    assert len(sample_organisation.letter_branding_pool) == 3
    assert branding_1 in sample_organisation.letter_branding_pool
    assert branding_2 in sample_organisation.letter_branding_pool
    assert branding_3 in sample_organisation.letter_branding_pool


def test_dao_add_letter_branding_list_to_organisation_pool_does_not_error_when_brand_already_in_pool(
    sample_organisation,
):
    branding_1 = create_letter_branding("branding_1", "filename_1")
    branding_2 = create_letter_branding("branding_2", "filename_2")
    branding_3 = create_letter_branding("branding_3", "filename_3")

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding_1.id, branding_2.id])

    assert sample_organisation.letter_branding_pool == [branding_1, branding_2]

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding_2.id, branding_3.id])

    assert sample_organisation.letter_branding_pool == [branding_1, branding_2, branding_3]


def test_dao_remove_letter_branding_from_organisation_pool(sample_organisation):
    branding_1 = create_letter_branding("branding_1", "filename_1")
    branding_2 = create_letter_branding("branding_2", "filename_2")
    branding_3 = create_letter_branding("branding_3", "filename_3")

    dao_add_letter_branding_list_to_organisation_pool(
        sample_organisation.id, [branding_1.id, branding_2.id, branding_3.id]
    )

    # branding_1 is the default for the org
    sample_organisation.letter_branding_id = branding_1.id

    # any branding in the pool can be removed
    dao_remove_letter_branding_from_organisation_pool(sample_organisation.id, branding_1.id)
    dao_remove_letter_branding_from_organisation_pool(sample_organisation.id, branding_2.id)

    # branding not in the pool raises an error
    with pytest.raises(ValueError):
        dao_remove_letter_branding_from_organisation_pool(sample_organisation.id, branding_2.id)

    assert sample_organisation.letter_branding_pool == [branding_3]
