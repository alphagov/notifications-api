import random
import uuid
from datetime import datetime, timedelta
from unittest.mock import ANY

import pytest
from flask import current_app
from freezegun import freeze_time
from sqlalchemy.exc import SQLAlchemyError

from app.constants import INVITE_ACCEPTED, INVITE_CANCELLED
from app.dao.email_branding_dao import dao_get_email_branding_by_id
from app.dao.letter_branding_dao import dao_get_letter_branding_by_id
from app.dao.organisation_dao import (
    dao_add_email_branding_to_organisation_pool,
    dao_add_letter_branding_list_to_organisation_pool,
    dao_add_service_to_organisation,
    dao_add_user_to_organisation,
)
from app.dao.services_dao import dao_archive_service, dao_fetch_service_by_id
from app.models import AnnualBilling, Organisation
from tests.app.db import (
    create_annual_billing,
    create_domain,
    create_email_branding,
    create_ft_billing,
    create_letter_branding,
    create_organisation,
    create_service,
    create_template,
    create_user,
)
from tests.utils import QueryRecorder


def test_get_all_organisations(admin_request, notify_db_session, nhs_email_branding, nhs_letter_branding):
    create_organisation(name="inactive org", active=False, organisation_type="nhs_central")
    create_organisation(name="active org", domains=["example.com"])

    response = admin_request.get("organisation.get_organisations", _expected_status=200)

    assert len(response) == 2
    assert (
        set(response[0].keys())
        == set(response[1].keys())
        == {
            "name",
            "id",
            "active",
            "count_of_live_services",
            "domains",
            "organisation_type",
        }
    )
    assert response[0]["name"] == "active org"
    assert response[0]["active"] is True
    assert response[0]["count_of_live_services"] == 0
    assert response[0]["domains"] == ["example.com"]
    assert response[0]["organisation_type"] is None
    assert response[1]["name"] == "inactive org"
    assert response[1]["active"] is False
    assert response[1]["count_of_live_services"] == 0
    assert response[1]["domains"] == []
    assert response[1]["organisation_type"] == "nhs_central"


def test_get_organisation_by_id(admin_request, notify_db_session):
    org = create_organisation()

    response = admin_request.get("organisation.get_organisation_by_id", _expected_status=200, organisation_id=org.id)

    assert set(response.keys()) == {
        "id",
        "name",
        "active",
        "crown",
        "organisation_type",
        "agreement_signed",
        "agreement_signed_at",
        "agreement_signed_by_id",
        "agreement_signed_version",
        "agreement_signed_on_behalf_of_name",
        "agreement_signed_on_behalf_of_email_address",
        "letter_branding_id",
        "email_branding_id",
        "domains",
        "request_to_go_live_notes",
        "count_of_live_services",
        "notes",
        "billing_contact_names",
        "billing_contact_email_addresses",
        "billing_reference",
        "purchase_order_number",
        "can_approve_own_go_live_requests",
        "permissions",
    }
    assert response["id"] == str(org.id)
    assert response["name"] == "test_org_1"
    assert response["active"] is True
    assert response["crown"] is None
    assert response["organisation_type"] is None
    assert response["agreement_signed"] is None
    assert response["agreement_signed_by_id"] is None
    assert response["agreement_signed_version"] is None
    assert response["letter_branding_id"] is None
    assert response["email_branding_id"] is None
    assert response["domains"] == []
    assert response["request_to_go_live_notes"] is None
    assert response["count_of_live_services"] == 0
    assert response["agreement_signed_on_behalf_of_name"] is None
    assert response["agreement_signed_on_behalf_of_email_address"] is None
    assert response["notes"] is None
    assert response["billing_contact_names"] is None
    assert response["billing_contact_email_addresses"] is None
    assert response["billing_reference"] is None
    assert response["purchase_order_number"] is None
    assert response["can_approve_own_go_live_requests"] is False


def test_get_organisation_by_id_returns_domains(admin_request, notify_db_session):
    org = create_organisation(
        domains=[
            "foo.gov.uk",
            "bar.gov.uk",
        ]
    )

    response = admin_request.get("organisation.get_organisation_by_id", _expected_status=200, organisation_id=org.id)

    assert set(response["domains"]) == {
        "foo.gov.uk",
        "bar.gov.uk",
    }


@pytest.mark.parametrize(
    "domain, expected_status",
    (
        ("foo.gov.uk", 200),
        ("bar.gov.uk", 200),
        ("oof.gov.uk", 404),
        pytest.param(
            "rab.gov.uk",
            200,
            marks=pytest.mark.xfail(raises=AssertionError),
        ),
        (None, 400),
        ("personally.identifying.information@example.com", 400),
    ),
)
def test_get_organisation_by_domain(admin_request, notify_db_session, domain, expected_status):
    org = create_organisation()
    other_org = create_organisation("Other organisation")
    create_domain("foo.gov.uk", org.id)
    create_domain("bar.gov.uk", org.id)
    create_domain("rab.gov.uk", other_org.id)

    response = admin_request.get(
        "organisation.get_organisation_by_domain",
        _expected_status=expected_status,
        domain=domain,
    )

    if expected_status == 200:
        assert response["id"] == str(org.id)
    else:
        assert response["result"] == "error"


def test_organisation_search_finds_organisations(notify_db_session, admin_request):
    organisation_1 = create_organisation(name="ABCDEF")
    organisation_2 = create_organisation(name="ABCGHT")
    create_organisation(name="ZYSWVU")
    response = admin_request.get("organisation.search", name="ABC")
    assert sorted(response["data"], key=lambda x: x["id"]) == sorted(
        [organisation_1.serialize_for_list(), organisation_2.serialize_for_list()], key=lambda x: x["id"]
    )


def test_organisation_search_handles_no_results(notify_db_session, admin_request):
    create_organisation(name="ABCDEF")
    response = admin_request.get("organisation.search", name="1234")
    assert response["data"] == []


def test_organisation_search_handles_special_characters(notify_db_session, admin_request):
    create_organisation(name="ABCDEF")
    organisation_2 = create_organisation(name="ZYX % WVU")
    create_organisation(name="123456")
    response = admin_request.get("organisation.search", name="%")
    assert response["data"] == [organisation_2.serialize_for_list()]


def test_organisation_search_handles_no_organisation_name(notify_db_session, admin_request):
    admin_request.get("organisation.search", _expected_status=400)


@pytest.mark.parametrize("crown", [True, False])
def test_post_create_organisation(admin_request, notify_db_session, crown):
    data = {
        "name": "test organisation",
        "active": True,
        "crown": crown,
        "organisation_type": "local",
    }

    response = admin_request.post("organisation.create_organisation", _data=data, _expected_status=201)

    organisations = Organisation.query.all()

    assert data["name"] == response["name"]
    assert data["active"] == response["active"]
    assert data["crown"] == response["crown"]
    assert data["organisation_type"] == response["organisation_type"]

    assert len(organisations) == 1
    # check that for non-nhs orgs, default branding is not set
    assert organisations[0].email_branding_id is None


@pytest.mark.parametrize("org_type", ["nhs_central", "nhs_local", "nhs_gp"])
def test_post_create_organisation_sets_default_nhs_branding_and_adds_it_to_org_pool_for_nhs_org_types(
    admin_request, notify_db_session, nhs_email_branding, nhs_letter_branding, org_type
):
    data = {
        "name": "test organisation",
        "active": True,
        "crown": False,
        "organisation_type": org_type,
    }

    admin_request.post("organisation.create_organisation", _data=data, _expected_status=201)

    organisation = Organisation.query.one()
    email_branding_nhs = dao_get_email_branding_by_id(current_app.config["NHS_EMAIL_BRANDING_ID"])
    letter_branding_nhs = dao_get_letter_branding_by_id(current_app.config["NHS_LETTER_BRANDING_ID"])

    assert organisation.email_branding_id == uuid.UUID(current_app.config["NHS_EMAIL_BRANDING_ID"])
    assert organisation.letter_branding_id == uuid.UUID(current_app.config["NHS_LETTER_BRANDING_ID"])

    assert organisation.email_branding_pool == [email_branding_nhs]
    assert organisation.letter_branding_pool == [letter_branding_nhs]


def test_post_create_organisation_existing_name_raises_400(admin_request, sample_organisation):
    data = {
        "name": sample_organisation.name,
        "active": True,
        "crown": True,
        "organisation_type": "central",
    }

    response = admin_request.post("organisation.create_organisation", _data=data, _expected_status=400)

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert response["message"] == "Organisation name already exists"


@pytest.mark.parametrize(
    "data, expected_error",
    (
        (
            {
                "active": False,
                "crown": True,
                "organisation_type": "central",
            },
            "name is a required property",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "organisation_type": "central",
            },
            "crown is a required property",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "crown": True,
            },
            "organisation_type is a required property",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "crown": None,
                "organisation_type": "central",
            },
            "crown None is not of type boolean",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "crown": False,
                "organisation_type": "foo",
            },
            (
                "organisation_type foo is not one of "
                "[central, local, nhs_central, nhs_local, nhs_gp, emergency_service, school_or_college, "
                "other]"
            ),
        ),
    ),
)
def test_post_create_organisation_with_missing_data_gives_validation_error(
    admin_request,
    notify_db_session,
    data,
    expected_error,
):
    response = admin_request.post("organisation.create_organisation", _data=data, _expected_status=400)

    assert len(response["errors"]) == 1
    assert response["errors"][0]["error"] == "ValidationError"
    assert response["errors"][0]["message"] == expected_error


@pytest.mark.parametrize("crown", (None, True, False))
@pytest.mark.parametrize("can_approve_own_go_live_requests", (True, False))
def test_post_update_organisation_updates_fields(
    admin_request,
    notify_db_session,
    crown,
    can_approve_own_go_live_requests,
):
    org = create_organisation()
    data = {
        "name": "new organisation name",
        "active": False,
        "crown": crown,
        "organisation_type": "central",
        "can_approve_own_go_live_requests": can_approve_own_go_live_requests,
    }
    assert org.crown is None

    admin_request.post("organisation.update_organisation", _data=data, organisation_id=org.id, _expected_status=204)

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert organisation[0].id == org.id
    assert organisation[0].name == data["name"]
    assert organisation[0].active == data["active"]
    assert organisation[0].crown == crown
    assert organisation[0].domains == []
    assert organisation[0].organisation_type == "central"
    assert organisation[0].can_approve_own_go_live_requests == can_approve_own_go_live_requests


@pytest.mark.parametrize(
    "domain_list",
    (
        ["example.com"],
        ["example.com", "example.org", "example.net"],
        [],
    ),
)
def test_post_update_organisation_updates_domains(
    admin_request,
    notify_db_session,
    domain_list,
):
    org = create_organisation(name="test_org_2")
    data = {
        "domains": domain_list,
    }

    admin_request.post("organisation.update_organisation", _data=data, organisation_id=org.id, _expected_status=204)

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert [domain.domain for domain in organisation[0].domains] == domain_list


def test_update_other_organisation_attributes_doesnt_clear_domains(
    admin_request,
    notify_db_session,
):
    org = create_organisation(name="test_org_2")
    create_domain("example.gov.uk", org.id)

    admin_request.post(
        "organisation.update_organisation",
        _data={
            "crown": True,
        },
        organisation_id=org.id,
        _expected_status=204,
    )

    assert [domain.domain for domain in org.domains] == ["example.gov.uk"]


@pytest.mark.parametrize("new_org_type", ["nhs_central", "nhs_local", "nhs_gp"])
def test_post_update_organisation_to_nhs_type_updates_branding_if_none_present(
    admin_request, nhs_email_branding, nhs_letter_branding, notify_db_session, new_org_type
):
    org = create_organisation(organisation_type="central")
    data = {
        "organisation_type": new_org_type,
    }

    admin_request.post("organisation.update_organisation", _data=data, organisation_id=org.id, _expected_status=204)

    organisation = Organisation.query.one()

    assert organisation.id == org.id
    assert organisation.organisation_type == new_org_type
    assert organisation.email_branding_id == uuid.UUID(current_app.config["NHS_EMAIL_BRANDING_ID"])
    assert organisation.letter_branding_id == uuid.UUID(current_app.config["NHS_LETTER_BRANDING_ID"])


@pytest.mark.parametrize("new_org_type", ["nhs_central", "nhs_local", "nhs_gp"])
def test_post_update_organisation_to_nhs_type_does_not_update_branding_if_default_branding_set(
    admin_request, nhs_email_branding, nhs_letter_branding, notify_db_session, new_org_type
):
    current_email_branding = create_email_branding(logo="example.png", name="custom branding")
    current_letter_branding = create_letter_branding()
    org = create_organisation(
        organisation_type="central",
        email_branding_id=current_email_branding.id,
        letter_branding_id=current_letter_branding.id,
    )
    data = {
        "organisation_type": new_org_type,
    }

    admin_request.post("organisation.update_organisation", _data=data, organisation_id=org.id, _expected_status=204)

    organisation = Organisation.query.one()

    assert organisation.id == org.id
    assert organisation.organisation_type == new_org_type
    assert organisation.email_branding_id == current_email_branding.id
    assert organisation.letter_branding_id == current_letter_branding.id


def test_update_organisation_default_branding(
    admin_request,
    notify_db_session,
):
    org = create_organisation(name="Test Organisation")

    email_branding = create_email_branding()
    letter_branding = create_letter_branding()

    assert org.email_branding is None
    assert org.letter_branding is None

    admin_request.post(
        "organisation.update_organisation",
        _data={
            "email_branding_id": str(email_branding.id),
            "letter_branding_id": str(letter_branding.id),
        },
        organisation_id=org.id,
        _expected_status=204,
    )

    assert org.email_branding == email_branding
    assert org.letter_branding == letter_branding


def test_post_update_organisation_raises_400_on_existing_org_name(admin_request, sample_organisation):
    org = create_organisation()
    data = {"name": sample_organisation.name, "active": False}

    response = admin_request.post(
        "organisation.update_organisation", _data=data, organisation_id=org.id, _expected_status=400
    )

    assert response["message"] == "Organisation name already exists"


def test_post_update_organisation_gives_404_status_if_org_does_not_exist(admin_request, notify_db_session):
    data = {"name": "new organisation name"}

    admin_request.post(
        "organisation.update_organisation",
        _data=data,
        organisation_id="31d42ce6-3dac-45a7-95cb-94423d5ca03c",
        _expected_status=404,
    )

    organisation = Organisation.query.all()

    assert not organisation


def test_post_update_organisation_returns_400_if_domain_is_duplicate(admin_request, notify_db_session):
    org = create_organisation()
    org2 = create_organisation(name="Second org")
    create_domain("same.com", org.id)

    data = {"domains": ["new.com", "same.com"]}

    response = admin_request.post(
        "organisation.update_organisation", _data=data, organisation_id=org2.id, _expected_status=400
    )

    assert response["message"] == "Domain already exists"


def test_post_update_organisation_set_mou_doesnt_email_if_no_signed_by(sample_organisation, admin_request, mocker):
    queue_mock = mocker.patch("app.organisation.rest.send_notification_to_queue")

    data = {"agreement_signed": True}

    admin_request.post(
        "organisation.update_organisation", _data=data, organisation_id=sample_organisation.id, _expected_status=204
    )

    assert queue_mock.called is False


@pytest.mark.parametrize(
    "on_behalf_of_name, on_behalf_of_email_address, templates_and_recipients",
    [
        (
            None,
            None,
            {
                "MOU_SIGNER_RECEIPT_TEMPLATE_ID": "notify@digital.cabinet-office.gov.uk",
            },
        ),
        (
            "Important Person",
            "important@person.com",
            {
                "MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID": "important@person.com",
                "MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID": "notify@digital.cabinet-office.gov.uk",
            },
        ),
    ],
)
def test_post_update_organisation_set_mou_emails_signed_by(
    sample_organisation,
    admin_request,
    mou_signed_templates,
    mocker,
    sample_user,
    on_behalf_of_name,
    on_behalf_of_email_address,
    templates_and_recipients,
    hostnames,
):
    queue_mock = mocker.patch("app.organisation.rest.send_notification_to_queue")
    sample_organisation.agreement_signed_on_behalf_of_name = on_behalf_of_name
    sample_organisation.agreement_signed_on_behalf_of_email_address = on_behalf_of_email_address

    admin_request.post(
        "organisation.update_organisation",
        _data={"agreement_signed": True, "agreement_signed_by_id": str(sample_user.id)},
        organisation_id=sample_organisation.id,
        _expected_status=204,
    )

    notifications = [x[0][0] for x in queue_mock.call_args_list]
    assert {n.template.name: n.to for n in notifications} == templates_and_recipients

    for n in notifications:
        # we pass in the same personalisation for all templates (though some templates don't use all fields)
        assert n.personalisation == {
            "mou_link": f"{hostnames.admin}/agreement/non-crown.pdf",
            "org_name": "sample organisation",
            "org_dashboard_link": f"{hostnames.admin}/organisations/{sample_organisation.id}",
            "signed_by_name": "Test User",
            "on_behalf_of_name": on_behalf_of_name,
        }


@pytest.mark.parametrize("invited_user_status", [INVITE_CANCELLED, INVITE_ACCEPTED])
def test_archive_organisation_sets_active_to_false(
    admin_request,
    sample_organisation,
    sample_invited_org_user,
    invited_user_status,
):
    # Invited users with 'cancelled' or 'accepted' don't stop orgs from being archived
    sample_invited_org_user.status = invited_user_status

    assert sample_organisation.active

    admin_request.post(
        "organisation.archive_organisation", organisation_id=sample_organisation.id, _expected_status=204
    )

    assert not sample_organisation.active


def test_archive_organisation_raises_an_error_if_org_has_team_members(
    admin_request,
    sample_organisation,
    sample_user,
):
    dao_add_user_to_organisation(sample_organisation.id, sample_user.id, permissions=[])

    response = admin_request.post(
        "organisation.archive_organisation", organisation_id=sample_organisation.id, _expected_status=400
    )
    assert response["message"] == "Cannot archive an organisation with team members or invited team members"

    assert sample_organisation.active


def test_archive_organisation_raises_an_error_if_org_has_pending_invited_team_members(
    admin_request,
    sample_organisation,
    sample_invited_org_user,
):
    response = admin_request.post(
        "organisation.archive_organisation", organisation_id=sample_organisation.id, _expected_status=400
    )
    assert response["message"] == "Cannot archive an organisation with team members or invited team members"

    assert sample_organisation.active


@pytest.mark.parametrize(
    "service_active, service_trial_mode",
    [
        (True, True),
        (False, True),
        (False, False),
        (True, False),
    ],
)
def test_archive_organisation_raises_an_error_if_org_has_services(
    admin_request,
    sample_organisation,
    sample_service,
    service_active,
    service_trial_mode,
):
    sample_service.active = service_active
    sample_service.restricted = service_trial_mode
    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    response = admin_request.post(
        "organisation.archive_organisation", organisation_id=sample_organisation.id, _expected_status=400
    )
    assert response["message"] == "Cannot archive an organisation with services"

    assert sample_organisation.active


def test_post_link_service_to_organisation(admin_request, sample_service):
    data = {"service_id": str(sample_service.id)}
    organisation = create_organisation(organisation_type="central")

    admin_request.post(
        "organisation.link_service_to_organisation", _data=data, organisation_id=organisation.id, _expected_status=204
    )
    assert len(organisation.services) == 1
    assert sample_service.organisation_type == "central"


@freeze_time("2021-09-24 13:30")
def test_post_link_service_to_organisation_inserts_annual_billing(admin_request, sample_service):
    data = {"service_id": str(sample_service.id)}
    organisation = create_organisation(organisation_type="central")
    assert len(organisation.services) == 0
    assert len(AnnualBilling.query.all()) == 0
    admin_request.post(
        "organisation.link_service_to_organisation", _data=data, organisation_id=organisation.id, _expected_status=204
    )

    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1
    assert annual_billing[0].free_sms_fragment_limit == 150000


def test_post_link_service_to_organisation_rollback_service_if_annual_billing_update_fails(
    admin_request, sample_service, mocker
):
    mocker.patch("app.dao.annual_billing_dao.dao_create_or_update_annual_billing_for_year", side_effect=SQLAlchemyError)
    data = {"service_id": str(sample_service.id)}
    assert not sample_service.organisation_type

    organisation = create_organisation(organisation_type="central")
    assert len(organisation.services) == 0
    assert len(AnnualBilling.query.all()) == 0
    with pytest.raises(expected_exception=SQLAlchemyError):
        admin_request.post("organisation.link_service_to_organisation", _data=data, organisation_id=organisation.id)
    assert not sample_service.organisation_type
    assert len(organisation.services) == 0
    assert len(AnnualBilling.query.all()) == 0


@freeze_time("2021-09-24 13:30")
def test_post_link_service_to_another_org(admin_request, sample_service, sample_organisation):
    data = {"service_id": str(sample_service.id)}
    assert len(sample_organisation.services) == 0
    assert not sample_service.organisation_type
    admin_request.post(
        "organisation.link_service_to_organisation",
        _data=data,
        organisation_id=sample_organisation.id,
        _expected_status=204,
    )

    assert len(sample_organisation.services) == 1
    assert not sample_service.organisation_type

    new_org = create_organisation(organisation_type="central")
    admin_request.post(
        "organisation.link_service_to_organisation", _data=data, organisation_id=new_org.id, _expected_status=204
    )
    assert not sample_organisation.services
    assert len(new_org.services) == 1
    assert sample_service.organisation_type == "central"
    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1
    assert annual_billing[0].free_sms_fragment_limit == 150000


def test_post_link_service_to_organisation_nonexistent_organisation(admin_request, sample_service, fake_uuid):
    data = {"service_id": str(sample_service.id)}

    admin_request.post(
        "organisation.link_service_to_organisation", _data=data, organisation_id=fake_uuid, _expected_status=404
    )


def test_post_link_service_to_organisation_nonexistent_service(admin_request, sample_organisation, fake_uuid):
    data = {"service_id": fake_uuid}

    admin_request.post(
        "organisation.link_service_to_organisation",
        _data=data,
        organisation_id=str(sample_organisation.id),
        _expected_status=404,
    )


def test_post_link_service_to_organisation_missing_payload(admin_request, sample_organisation, fake_uuid):
    admin_request.post(
        "organisation.link_service_to_organisation", organisation_id=str(sample_organisation.id), _expected_status=400
    )


def test_rest_get_organisation_services(admin_request, sample_organisation, sample_service):
    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    response = admin_request.get(
        "organisation.get_organisation_services", organisation_id=str(sample_organisation.id), _expected_status=200
    )

    assert response == [sample_service.serialize_for_org_dashboard()]


def test_rest_get_organisation_services_is_ordered_by_name(admin_request, sample_organisation, sample_service):
    service_2 = create_service(service_name="service 2")
    service_1 = create_service(service_name="service 1")
    dao_add_service_to_organisation(service_1, sample_organisation.id)
    dao_add_service_to_organisation(service_2, sample_organisation.id)
    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    response = admin_request.get(
        "organisation.get_organisation_services", organisation_id=str(sample_organisation.id), _expected_status=200
    )

    assert response[0]["name"] == sample_service.name
    assert response[1]["name"] == service_1.name
    assert response[2]["name"] == service_2.name


def test_rest_get_organisation_services_inactive_services_at_end(admin_request, sample_organisation):
    inactive_service = create_service(service_name="inactive service", active=False)
    service = create_service()
    inactive_service_1 = create_service(service_name="inactive service 1", active=False)

    dao_add_service_to_organisation(inactive_service, sample_organisation.id)
    dao_add_service_to_organisation(service, sample_organisation.id)
    dao_add_service_to_organisation(inactive_service_1, sample_organisation.id)

    response = admin_request.get(
        "organisation.get_organisation_services", organisation_id=str(sample_organisation.id), _expected_status=200
    )

    assert response[0]["name"] == service.name
    assert response[1]["name"] == inactive_service.name
    assert response[2]["name"] == inactive_service_1.name


def test_add_user_to_organisation_returns_added_user(admin_request, sample_organisation, sample_user):
    response = admin_request.post(
        "organisation.add_user_to_organisation",
        organisation_id=str(sample_organisation.id),
        user_id=str(sample_user.id),
        _data={"permissions": []},
        _expected_status=200,
    )

    assert response["data"]["id"] == str(sample_user.id)
    assert len(response["data"]["organisations"]) == 1
    assert response["data"]["organisations"][0] == str(sample_organisation.id)


def test_add_user_to_organisation_returns_404_if_user_does_not_exist(admin_request, sample_organisation):
    admin_request.post(
        "organisation.add_user_to_organisation",
        organisation_id=str(sample_organisation.id),
        user_id=str(uuid.uuid4()),
        _data={"permissions": []},
        _expected_status=404,
    )


def test_remove_user_from_organisation(admin_request, sample_organisation, sample_user):
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=sample_user.id, permissions=[])

    admin_request.delete(
        "organisation.remove_user_from_organisation", organisation_id=sample_organisation.id, user_id=sample_user.id
    )

    assert sample_organisation.users == []


def test_remove_user_from_organisation_when_user_is_not_an_org_member(admin_request, sample_organisation, sample_user):
    resp = admin_request.delete(
        "organisation.remove_user_from_organisation",
        organisation_id=sample_organisation.id,
        user_id=sample_user.id,
        _expected_status=404,
    )

    assert resp == {"result": "error", "message": "User not found"}


def test_get_organisation_users_returns_users_for_organisation(admin_request, sample_organisation):
    first = create_user(email="first@invited.com")
    second = create_user(email="another@invited.com")
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=first.id, permissions=[])
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=second.id, permissions=[])

    response = admin_request.get(
        "organisation.get_organisation_users", organisation_id=sample_organisation.id, _expected_status=200
    )

    assert len(response["data"]) == 2
    assert response["data"][0]["id"] == str(first.id)


@freeze_time("2020-02-24 13:30")
def test_get_organisation_services_usage(admin_request, notify_db_session, mocker):
    org = create_organisation(name="Organisation without live services")
    service = create_service()
    template = create_template(service=service)
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2019)
    create_ft_billing(
        bst_date=datetime.utcnow().date(), template=template, billable_unit=19, rate=0.060, notifications_sent=19
    )
    mocker.patch(
        "app.dao.fact_billing_dao.get_ft_billing_data_for_today_updated_at", return_value="2019-06-01T12:00:00+00:00"
    )
    with freeze_time("2019-06-01"):
        response = admin_request.get(
            "organisation.get_organisation_services_usage", organisation_id=org.id, **{"year": 2019}
        )
    assert len(response) == 2
    assert len(response["services"]) == 1
    service_usage = response["services"][0]
    assert service_usage["service_id"] == str(service.id)
    assert service_usage["service_name"] == service.name
    assert service_usage["chargeable_billable_sms"] == 9.0
    assert service_usage["emails_sent"] == 0
    assert service_usage["free_sms_limit"] == 10
    assert service_usage["letter_cost"] == 0
    assert service_usage["sms_billable_units"] == 19
    assert service_usage["sms_remainder"] == 0
    assert service_usage["sms_cost"] == 0.54
    assert response["updated_at"] == "2019-06-01T12:00:00+00:00"


@pytest.mark.parametrize("num_services", [1, 5, 10])
@freeze_time("2020-02-24 13:30")
def test_get_organisation_services_usage_limit_queries_executed(admin_request, notify_db_session, num_services):
    org = create_organisation(name="Organisation without live services")
    for _ in range(num_services):
        service = create_service(service_name=f"service {_}")
        template = create_template(service=service)
        dao_add_service_to_organisation(service=service, organisation_id=org.id)
        create_annual_billing(service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2019)
        for num_billing_days in range(random.randint(10, 25)):
            create_ft_billing(
                bst_date=datetime.utcnow().date() - timedelta(days=num_billing_days),
                template=template,
                billable_unit=num_billing_days + 1,
                rate=0.060,
                notifications_sent=num_billing_days + 1,
            )

    with QueryRecorder() as query_recorder:
        admin_request.get("organisation.get_organisation_services_usage", organisation_id=org.id, **{"year": 2019})

    assert len(query_recorder.queries) == 5, (
        "The number of queries executed by this view has changed. The number of queries executed "
        "shouldn't increase as the number of org services increases. If this has increased by 1 or 2 queries, and "
        "affects all parameterized versions of this test, you can probably accept the change. If only one of the "
        "test runs is failing, you may want to look at the new code instead."
    )


@freeze_time("2020-02-24 13:30")
def test_get_organisation_services_usage_sort_active_first(admin_request, notify_db_session):
    org = create_organisation(name="Organisation without live services")
    service = create_service(service_name="live service")
    archived_service = create_service(service_name="archived_service")
    template = create_template(service=service)
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    dao_add_service_to_organisation(service=archived_service, organisation_id=org.id)
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2019)
    create_ft_billing(
        bst_date=datetime.utcnow().date(), template=template, billable_unit=19, rate=0.060, notifications_sent=19
    )
    response = admin_request.get(
        "organisation.get_organisation_services_usage", organisation_id=org.id, **{"year": 2019}
    )
    assert len(response) == 2
    assert len(response["services"]) == 2
    first_service = response["services"][0]
    assert first_service["service_id"] == str(archived_service.id)
    assert first_service["service_name"] == archived_service.name
    assert first_service["active"] is True
    last_service = response["services"][1]
    assert last_service["service_id"] == str(service.id)
    assert last_service["service_name"] == service.name
    assert last_service["active"] is True
    assert response["updated_at"] is None

    dao_archive_service(service_id=archived_service.id)
    response_after_archive = admin_request.get(
        "organisation.get_organisation_services_usage", organisation_id=org.id, **{"year": 2019}
    )
    first_service = response_after_archive["services"][0]
    assert first_service["service_id"] == str(service.id)
    assert first_service["service_name"] == service.name
    assert first_service["active"] is True
    last_service = response_after_archive["services"][1]
    assert last_service["service_id"] == str(archived_service.id)
    assert last_service["service_name"] == archived_service.name
    assert last_service["active"] is False


def test_get_organisation_services_usage_returns_400_if_year_is_invalid(admin_request):
    response = admin_request.get(
        "organisation.get_organisation_services_usage",
        organisation_id=uuid.uuid4(),
        **{"year": "not-a-valid-year"},
        _expected_status=400,
    )
    assert response["message"] == "No valid year provided"


def test_get_organisation_services_usage_returns_400_if_year_is_empty(admin_request):
    response = admin_request.get(
        "organisation.get_organisation_services_usage", organisation_id=uuid.uuid4(), _expected_status=400
    )
    assert response["message"] == "No valid year provided"


def test_get_organisation_email_branding_pool_returns_email_brandings_for_organisation(
    admin_request, sample_organisation
):
    first_branding = create_email_branding(colour="blue", logo="test_x1.png", name="email_branding_1")
    second_branding = create_email_branding(colour="indigo", logo="test_x2.png", name="email_branding_2")

    dao_add_email_branding_to_organisation_pool(
        organisation_id=sample_organisation.id, email_branding_id=first_branding.id
    )
    dao_add_email_branding_to_organisation_pool(
        organisation_id=sample_organisation.id, email_branding_id=second_branding.id
    )

    response = admin_request.get(
        "organisation.get_organisation_email_branding_pool",
        organisation_id=sample_organisation.id,
        _expected_status=200,
    )

    assert len(response["data"]) == 2
    assert response["data"][0]["id"] == str(first_branding.id)
    assert response["data"][1]["id"] == str(second_branding.id)


def test_update_organisation_email_branding_pool_raises_an_error_when_data_not_in_required_format(
    admin_request,
    sample_organisation,
):
    admin_request.post(
        "organisation.update_organisation_email_branding_pool",
        organisation_id=sample_organisation.id,
        _data="invalid",
        _expected_status=400,
    )


def test_update_organisation_email_branding_pool_updates_branding_pool(
    admin_request,
    sample_organisation,
):
    branding_1 = create_email_branding(logo="test_x1.png", name="email_branding_1")
    branding_2 = create_email_branding(logo="test_x2.png", name="email_branding_2")

    admin_request.post(
        "organisation.update_organisation_email_branding_pool",
        organisation_id=sample_organisation.id,
        _data={"branding_ids": [str(branding_1.id), str(branding_2.id)]},
        _expected_status=204,
    )
    assert len(sample_organisation.email_branding_pool) == 2


def test_remove_email_branding_from_organisation_pool(
    admin_request,
    sample_organisation,
):
    first_branding = create_email_branding(colour="blue", logo="test_x1.png", name="email_branding_1")
    second_branding = create_email_branding(colour="indigo", logo="test_x2.png", name="email_branding_2")

    dao_add_email_branding_to_organisation_pool(
        organisation_id=sample_organisation.id, email_branding_id=first_branding.id
    )
    dao_add_email_branding_to_organisation_pool(
        organisation_id=sample_organisation.id, email_branding_id=second_branding.id
    )
    assert set(sample_organisation.email_branding_pool) == {first_branding, second_branding}

    admin_request.delete(
        "organisation.remove_email_branding_from_organisation_pool",
        organisation_id=sample_organisation.id,
        email_branding_id=first_branding.id,
        _expected_status=204,
    )
    assert sample_organisation.email_branding_pool == [second_branding]


def test_remove_email_branding_from_organisation_pool_cannot_remove_branding_not_in_pool(
    admin_request,
    sample_organisation,
):
    first_branding = create_email_branding(colour="blue", logo="test_x1.png", name="email_branding_1")
    second_branding = create_email_branding(colour="indigo", logo="test_x2.png", name="email_branding_2")

    dao_add_email_branding_to_organisation_pool(
        organisation_id=sample_organisation.id, email_branding_id=first_branding.id
    )
    assert sample_organisation.email_branding_pool == [first_branding]

    admin_request.delete(
        "organisation.remove_email_branding_from_organisation_pool",
        organisation_id=sample_organisation.id,
        email_branding_id=second_branding.id,
        _expected_status=404,
    )
    assert sample_organisation.email_branding_pool == [first_branding]


def test_remove_email_branding_from_organisation_pool_cannot_remove_default_branding(
    admin_request,
    sample_organisation,
):
    branding = create_email_branding(colour="blue", logo="test_x1.png", name="email_branding_1")

    dao_add_email_branding_to_organisation_pool(organisation_id=sample_organisation.id, email_branding_id=branding.id)
    sample_organisation.email_branding_id = branding.id

    admin_request.delete(
        "organisation.remove_email_branding_from_organisation_pool",
        organisation_id=sample_organisation.id,
        email_branding_id=branding.id,
        _expected_status=400,
    )
    assert sample_organisation.email_branding_pool == [branding]


def test_get_organisation_letter_branding_pool_returns_letter_brandings_for_organisation(
    admin_request, sample_organisation
):
    branding_1 = create_letter_branding("nhs", "nhs.svg")
    branding_2 = create_letter_branding("cabinet_office", "cabinet_office.svg")

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding_1.id, branding_2.id])

    response = admin_request.get(
        "organisation.get_organisation_letter_branding_pool",
        organisation_id=sample_organisation.id,
    )

    assert len(response["data"]) == 2
    assert response["data"][0]["id"] == str(branding_2.id)
    assert response["data"][1]["id"] == str(branding_1.id)


def test_update_organisation_letter_branding_pool_raises_an_error_when_data_not_in_required_format(
    admin_request,
    sample_organisation,
):
    admin_request.post(
        "organisation.update_organisation_letter_branding_pool",
        organisation_id=sample_organisation.id,
        _data="invalid",
        _expected_status=400,
    )


def test_update_organisation_letter_branding_pool_updates_branding_pool(
    admin_request,
    sample_organisation,
):
    branding_1 = create_letter_branding("letter_branding_1", "filename_1")
    branding_2 = create_letter_branding("letter_branding_2", "filename_2")

    admin_request.post(
        "organisation.update_organisation_letter_branding_pool",
        organisation_id=sample_organisation.id,
        _data={"branding_ids": [str(branding_1.id), str(branding_2.id)]},
        _expected_status=204,
    )
    assert len(sample_organisation.letter_branding_pool) == 2


def test_remove_letter_branding_from_organisation_pool(admin_request, sample_organisation):
    branding_1 = create_letter_branding("letter_branding_1", "filename_1")
    branding_2 = create_letter_branding("letter_branding_2", "filename_2")

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding_1.id, branding_2.id])

    admin_request.delete(
        "organisation.remove_letter_branding_from_organisation_pool",
        organisation_id=sample_organisation.id,
        letter_branding_id=branding_1.id,
    )
    assert sample_organisation.letter_branding_pool == [branding_2]


def test_remove_letter_branding_from_organisation_pool_cannot_remove_branding_not_in_pool(
    admin_request,
    sample_organisation,
):
    branding_1 = create_letter_branding("letter_branding_1", "filename_1")
    branding_2 = create_letter_branding("letter_branding_2", "filename_2")

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding_1.id])

    assert sample_organisation.letter_branding_pool == [branding_1]

    response = admin_request.delete(
        "organisation.remove_letter_branding_from_organisation_pool",
        organisation_id=sample_organisation.id,
        letter_branding_id=branding_2.id,
        _expected_status=404,
    )

    assert response["message"] == f"Letter branding {branding_2.id} not in sample organisation's pool"
    assert sample_organisation.letter_branding_pool == [branding_1]


def test_remove_letter_branding_from_organisation_pool_cannot_remove_default_branding(
    admin_request,
    sample_organisation,
):
    branding = create_letter_branding("letter_branding_1", "filename_1")

    dao_add_letter_branding_list_to_organisation_pool(sample_organisation.id, [branding.id])
    sample_organisation.letter_branding_id = branding.id

    response = admin_request.delete(
        "organisation.remove_letter_branding_from_organisation_pool",
        organisation_id=sample_organisation.id,
        letter_branding_id=branding.id,
        _expected_status=400,
    )
    assert response["message"] == "You cannot remove an organisation's default letter branding"
    assert sample_organisation.letter_branding_pool == [branding]


def test_notify_org_users_of_request_to_go_live(
    mocker,
    admin_request,
    notify_service,
    sample_organisation,
    sample_service,
    organisation_has_new_go_live_request_template,
    hostnames,
):
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    go_live_user = create_user(email="go-live-user@example.gov.uk", name="Go live user")
    first_org_user = create_user(email="first-org-user@example.gov.uk", name="First org user")
    second_org_user = create_user(email="second-org-user@example.gov.uk", name="Second org user")
    dao_add_user_to_organisation(
        organisation_id=sample_organisation.id, user_id=first_org_user.id, permissions=["can_make_services_live"]
    )
    dao_add_user_to_organisation(
        organisation_id=sample_organisation.id, user_id=second_org_user.id, permissions=["can_make_services_live"]
    )

    notifications = [object(), object()]

    mock_persist_notification = mocker.patch(
        "app.organisation.sender.persist_notification",
        side_effect=notifications,
    )
    mock_send_notification_to_queue = mocker.patch(
        "app.organisation.sender.send_notification_to_queue",
    )
    sample_service.organisation = sample_organisation
    sample_service.go_live_user = go_live_user

    admin_request.post(
        "organisation.notify_users_of_request_to_go_live",
        service_id=sample_service.id,
        _expected_status=204,
    )

    assert {
        (call[1]["recipient"], call[1]["personalisation"]["name"]) for call in mock_persist_notification.call_args_list
    } == {
        ("first-org-user@example.gov.uk", "First org user"),
        ("second-org-user@example.gov.uk", "Second org user"),
    }

    for call in mock_persist_notification.call_args_list:
        assert call[1] == dict(
            template_id=uuid.UUID("5c7cfc0f-c3f4-4bd6-9a84-5a144aad5425"),
            template_version=1,
            recipient=ANY,
            service=notify_service,
            personalisation={
                "service_name": "Sample service",
                "requester_name": "Go live user",
                "requester_email_address": "go-live-user@example.gov.uk",
                "make_service_live_link": f"{hostnames.admin}/services/{sample_service.id}/make-service-live",
                "support_page_link": f"{hostnames.admin}/support",
                "organisation_name": "sample organisation",
                "name": ANY,
            },
            notification_type="email",
            api_key_id=None,
            key_type="normal",
            reply_to_text="go-live-user@example.gov.uk",
        )

    assert mock_send_notification_to_queue.call_args_list == [
        call(notification, queue="notify-internal-tasks") for notification in notifications
    ]


def test_notify_org_users_of_request_to_go_live_requires_org_user_permission(
    mocker,
    admin_request,
    notify_service,
    sample_organisation,
    sample_service,
    organisation_has_new_go_live_request_template,
):
    go_live_user = create_user(email="go-live-user@example.gov.uk", name="Go live user")
    first_org_user = create_user(email="first-org-user@example.gov.uk", name="First org user")
    second_org_user = create_user(email="second-org-user@example.gov.uk", name="Second org user")
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=first_org_user.id, permissions=[])
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=second_org_user.id, permissions=[])

    notifications = [object(), object()]

    mock_persist_notification = mocker.patch(
        "app.organisation.sender.persist_notification",
        side_effect=notifications,
    )
    mock_send_notification_to_queue = mocker.patch(
        "app.organisation.sender.send_notification_to_queue",
    )
    sample_service.organisation = sample_organisation
    sample_service.go_live_user = go_live_user

    admin_request.post(
        "organisation.notify_users_of_request_to_go_live",
        service_id=sample_service.id,
        _expected_status=204,
    )

    assert mock_persist_notification.call_args_list == []
    assert mock_send_notification_to_queue.call_args_list == []


def test_notify_org_member_about_next_steps_of_go_live_request(
    mocker,
    admin_request,
    notify_service,
    sample_organisation,
    sample_service,
    organisation_next_steps_for_go_live_request_template,
    hostnames,
):
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    go_live_user = create_user(email="go-live-user@example.gov.uk", name="Go live user")
    first_org_user = create_user(email="first-org-user@example.gov.uk", name="First org user")
    second_org_user = create_user(email="second-org-user@example.gov.uk", name="Second org user")
    dao_add_user_to_organisation(
        organisation_id=sample_organisation.id, user_id=first_org_user.id, permissions=["can_make_services_live"]
    )
    dao_add_user_to_organisation(
        organisation_id=sample_organisation.id, user_id=second_org_user.id, permissions=["can_make_services_live"]
    )

    notifications = [object()]

    mock_persist_notification = mocker.patch(
        "app.organisation.rest.persist_notification",
        side_effect=notifications,
    )
    mock_send_notification_to_queue = mocker.patch(
        "app.organisation.rest.send_notification_to_queue",
    )
    sample_service.organisation = sample_organisation
    sample_service.has_active_go_live_request = True
    sample_service.go_live_user = go_live_user

    admin_request.post(
        "organisation.notify_org_member_about_next_steps_of_go_live_request",
        service_id=sample_service.id,
        _data={"to": "first-org-user@example.gov.uk", "service_name": "test service", "body": "blah blah blah"},
        _expected_status=204,
    )

    assert mock_persist_notification.call_count == 1
    assert mock_persist_notification.call_args_list[0][1]["recipient"] == "first-org-user@example.gov.uk"

    assert mock_persist_notification.call_args_list[0][1] == dict(
        template_id=uuid.UUID("62f12a62-742b-4458-9336-741521b131c7"),
        template_version=1,
        recipient="first-org-user@example.gov.uk",
        service=notify_service,
        personalisation={"service_name": "test service", "body": "blah blah blah"},
        notification_type="email",
        api_key_id=None,
        key_type="normal",
        reply_to_text="notify@gov.uk",
    )

    assert mock_send_notification_to_queue.call_args_list == [
        mocker.call(notification, queue="notify-internal-tasks") for notification in notifications
    ]


def test_notify_service_member_of_rejected_request_to_go_live(
    mocker,
    admin_request,
    notify_service,
    sample_organisation,
    sample_service,
    organisation_reject_go_live_request_template,
    hostnames,
):
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    go_live_user = create_user(email="go-live-user@example.gov.uk", name="Go live user")
    first_org_user = create_user(email="first-org-user@example.gov.uk", name="First org user")
    second_org_user = create_user(email="second-org-user@example.gov.uk", name="Second org user")
    dao_add_user_to_organisation(
        organisation_id=sample_organisation.id, user_id=first_org_user.id, permissions=["can_make_services_live"]
    )
    dao_add_user_to_organisation(
        organisation_id=sample_organisation.id, user_id=second_org_user.id, permissions=["can_make_services_live"]
    )

    notifications = [object()]

    mock_persist_notification = mocker.patch(
        "app.organisation.rest.persist_notification",
        side_effect=notifications,
    )
    mock_send_notification_to_queue = mocker.patch(
        "app.organisation.rest.send_notification_to_queue",
    )
    sample_service.organisation = sample_organisation
    sample_service.has_active_go_live_request = True
    sample_service.go_live_user = go_live_user

    personalisation = {
        "name": "Sam",
        "service_name": sample_service.name,
        "organisation_name": sample_organisation.name,
        "reason": "line 1\nline 2",
        "organisation_team_member_name": "First",
        "organisation_team_member_email": "first-org-user@example.gov.uk",
    }
    admin_request.post(
        "organisation.notify_service_member_of_rejected_go_live_request",
        service_id=sample_service.id,
        _data=personalisation,
        _expected_status=204,
    )

    assert mock_persist_notification.call_count == 1
    assert mock_persist_notification.call_args_list[0][1]["recipient"] == "go-live-user@example.gov.uk"

    assert mock_persist_notification.call_args_list[0][1] == dict(
        template_id=uuid.UUID("507d0796-9e23-4ad7-b83b-5efbd9496866"),
        template_version=1,
        recipient="go-live-user@example.gov.uk",
        service=notify_service,
        personalisation={**personalisation, "reason": "^ line 1\n^ line 2"},
        notification_type="email",
        api_key_id=None,
        key_type="normal",
        reply_to_text="notify@gov.uk",
    )

    assert mock_send_notification_to_queue.call_args_list == [
        mocker.call(notification, queue="notify-internal-tasks") for notification in notifications
    ]
