from datetime import UTC, datetime

import pytest
from freezegun import freeze_time

from app.constants import BRANDING_ORG
from app.dao.organisation_dao import (
    dao_add_email_branding_list_to_organisation_pool,
    dao_get_email_branding_pool_for_organisation,
)
from app.models import EmailBranding
from tests.app.db import (
    create_email_branding,
    create_organisation,
    create_service,
)


def test_get_email_branding_options(admin_request, notify_db_session):
    email_branding1 = EmailBranding(colour="#FFFFFF", logo="/path/image.png", name="Org1", alt_text="Org1")
    email_branding2 = EmailBranding(colour="#000000", logo="/path/other.png", name="Org2", alt_text="Org2")
    notify_db_session.add_all([email_branding1, email_branding2])
    notify_db_session.commit()

    email_branding = admin_request.get("email_branding.get_email_branding_options")["email_branding"]

    assert len(email_branding) == 2
    assert {email_branding["id"] for email_branding in email_branding} == {
        str(email_branding1.id),
        str(email_branding2.id),
    }


@freeze_time("2023-01-20T10:40:34Z")
@pytest.mark.parametrize(
    "created_at, expected_created_at, updated_at, expected_updated_at",
    (
        (
            datetime(2022, 12, 6, 14, 00),
            "2022-12-06T14:00:00.000000Z",
            datetime(2023, 1, 20, 11, 00),
            "2023-01-20T11:00:00.000000Z",
        ),
        (None, "2023-01-20T10:40:34.000000Z", None, None),
    ),
)
def test_get_email_branding_by_id(
    admin_request, notify_db_session, created_at, expected_created_at, updated_at, expected_updated_at
):
    email_branding = EmailBranding(
        colour="#FFFFFF",
        logo="/path/image.png",
        name="Some Org",
        text="My Org",
        created_at=created_at,
        updated_at=updated_at,
    )
    notify_db_session.add(email_branding)
    notify_db_session.commit()

    response = admin_request.get(
        "email_branding.get_email_branding_by_id", _expected_status=200, email_branding_id=email_branding.id
    )

    assert set(response["email_branding"].keys()) == {
        "colour",
        "logo",
        "name",
        "id",
        "text",
        "brand_type",
        "alt_text",
        "created_by",
        "created_at",
        "updated_at",
    }
    assert response["email_branding"]["colour"] == "#FFFFFF"
    assert response["email_branding"]["logo"] == "/path/image.png"
    assert response["email_branding"]["name"] == "Some Org"
    assert response["email_branding"]["text"] == "My Org"
    assert response["email_branding"]["id"] == str(email_branding.id)
    assert response["email_branding"]["brand_type"] == str(email_branding.brand_type)
    assert response["email_branding"]["alt_text"] is None
    assert response["email_branding"]["created_at"] == expected_created_at
    assert response["email_branding"]["updated_at"] == expected_updated_at


@freeze_time()
def test_post_create_email_branding(admin_request, notify_db_session):
    data = {
        "name": "test email_branding",
        "colour": "#0000ff",
        "logo": "/images/test_x2.png",
        "brand_type": BRANDING_ORG,
        "alt_text": None,
        "text": "some text",
    }
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)
    assert data["name"] == response["data"]["name"]
    assert data["colour"] == response["data"]["colour"]
    assert data["logo"] == response["data"]["logo"]
    assert data["brand_type"] == response["data"]["brand_type"]
    assert response["data"]["text"] == "some text"
    assert response["data"]["alt_text"] is None

    email_branding = EmailBranding.query.filter(EmailBranding.name == data["name"]).one()
    assert email_branding.created_by is None
    assert email_branding.created_at == datetime.now(UTC).replace(tzinfo=None)


@freeze_time()
def test_post_create_email_branding_with_created_fields(admin_request, notify_db_session, sample_user):
    data = {
        "name": "test email_branding",
        "alt_text": "test alt text",
        "colour": "#0000ff",
        "logo": "/images/test_x2.png",
        "brand_type": BRANDING_ORG,
        "created_by": str(sample_user.id),
    }
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)
    assert data["name"] == response["data"]["name"]
    assert data["colour"] == response["data"]["colour"]
    assert data["logo"] == response["data"]["logo"]
    assert data["brand_type"] == response["data"]["brand_type"]
    assert response["data"]["text"] is None

    email_branding = EmailBranding.query.filter(EmailBranding.name == data["name"]).one()
    assert str(email_branding.created_by) == data["created_by"]
    assert email_branding.created_at == datetime.now(UTC).replace(tzinfo=None)
    assert email_branding.text is None


def test_post_create_email_branding_without_brand_type_defaults(admin_request, notify_db_session):
    data = {
        "name": "test email_branding",
        "alt_text": "test alt text",
        "colour": "#0000ff",
        "logo": "/images/test_x2.png",
    }
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)
    assert BRANDING_ORG == response["data"]["brand_type"]


def test_post_create_email_branding_without_logo_is_ok(admin_request, notify_db_session):
    data = {
        "name": "test email_branding",
        "alt_text": "test alt text",
        "colour": "#0000ff",
    }
    response = admin_request.post(
        "email_branding.create_email_branding",
        _data=data,
        _expected_status=201,
    )
    assert not response["data"]["logo"]


@pytest.mark.parametrize(
    "data, expected_alt_text, expected_text",
    [
        ({"alt_text": None, "text": "some text"}, None, "some text"),
        ({"alt_text": "some alt text", "text": None}, "some alt text", None),
        ({"text": "some text"}, None, "some text"),
        ({"alt_text": "some alt text"}, "some alt text", None),
    ],
)
def test_post_create_email_branding_allows_one_of_alt_text_or_text_whether_null_or_missing(
    admin_request,
    notify_db_session,
    data,
    expected_alt_text,
    expected_text,
):
    data = data | {"name": "test email_branding"}
    admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)

    email_branding = EmailBranding.query.one()
    assert email_branding.alt_text == expected_alt_text
    assert email_branding.text == expected_text


@pytest.mark.parametrize(
    "data",
    [
        {"alt_text": None, "text": None},
        {"alt_text": "some alt text", "text": "some text"},
        {},
    ],
)
def test_post_create_email_branding_enforces_alt_text_and_text_one_null_one_provided(
    admin_request,
    notify_db_session,
    data,
):
    data = data | {"name": "test email_branding"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=400)

    assert response["message"] == "Email branding must have exactly one of alt_text and text."


def test_post_create_email_branding_returns_400_when_name_is_missing(admin_request, notify_db_session):
    data = {"text": "some text", "logo": "images/text_x2.png"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=400)

    assert response["errors"][0]["message"] == "name is a required property"


@pytest.mark.parametrize(
    "data_update",
    [
        ({"name": "test email_branding 1"}),
        ({"logo": "images/text_x3.png", "colour": "#ffffff"}),
    ],
)
def test_post_update_email_branding_updates_field(admin_request, notify_db_session, data_update):
    data = {"name": "test email_branding", "logo": "images/text_x2.png", "alt_text": "alt_text"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)

    email_branding_id = response["data"]["id"]

    admin_request.post("email_branding.update_email_branding", _data=data_update, email_branding_id=email_branding_id)

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert str(email_branding[0].id) == email_branding_id
    for key in data_update.keys():
        assert getattr(email_branding[0], key) == data_update[key]


@freeze_time(as_kwarg="frozen_time")
def test_post_update_email_branding_updated_fields(admin_request, notify_db_session, sample_user, **kwargs):
    frozen_time = kwargs["frozen_time"]
    start_time = frozen_time.time_to_freeze

    data = {"name": "test email_branding", "logo": "images/text_x2.png", "text": "some text"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)

    email_brandings = EmailBranding.query.all()
    email_branding = email_brandings[0]
    assert len(email_brandings) == 1
    assert email_branding.created_at == start_time
    assert email_branding.updated_by is None
    assert email_branding.updated_at is None

    frozen_time.tick()
    assert frozen_time.time_to_freeze != start_time

    email_branding_id = response["data"]["id"]
    update_data = {"name": "updated email branding name", "updated_by": str(sample_user.id)}

    admin_request.post(
        "email_branding.update_email_branding",
        _data=update_data,
        email_branding_id=email_branding_id,
    )

    email_brandings = EmailBranding.query.all()
    email_branding = email_brandings[0]
    assert len(email_brandings) == 1
    assert email_branding.created_at == start_time
    assert str(email_branding.updated_by) == update_data["updated_by"]
    assert email_branding.updated_at == frozen_time.time_to_freeze


def test_post_update_email_branding_rejects_none_value_for_name(admin_request, notify_db_session):
    email_branding = create_email_branding(name="foo")

    admin_request.post(
        "email_branding.update_email_branding",
        email_branding_id=email_branding.id,
        _data={"name": None},
        _expected_status=400,
    )


def test_create_email_branding_reject_invalid_brand_type(admin_request):
    data = {"name": "test email_branding", "brand_type": "NOT A TYPE"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=400)

    assert response["errors"][0]["message"] == "brand_type NOT A TYPE is not one of [org, both, org_banner]"


def test_create_email_branding_400s_on_unique_violation(admin_request, notify_db_session):
    data = {"name": "test email_branding", "logo": "images/text_x2.png", "text": "some text"}
    admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=400)

    assert response["message"]["name"] == ["An email branding with that name already exists."]


def test_update_email_branding_400s_on_unique_violation(admin_request, notify_db_session):
    create_email_branding(name="test 1")
    email_branding = create_email_branding(name="test 2")
    data = email_branding.serialize()
    data["name"] = "test 1"

    response = admin_request.post(
        "email_branding.update_email_branding", email_branding_id=data["id"], _data=data, _expected_status=400
    )

    assert response["message"]["name"] == ["An email branding with that name already exists."]


def test_update_email_branding_reject_invalid_brand_type(admin_request, notify_db_session):
    email_branding = create_email_branding()
    data = {"brand_type": "NOT A TYPE"}
    response = admin_request.post(
        "email_branding.update_email_branding", _data=data, _expected_status=400, email_branding_id=email_branding.id
    )

    assert response["errors"][0]["message"] == "brand_type NOT A TYPE is not one of [org, both, org_banner]"


@pytest.mark.parametrize(
    "data, expected_alt_text, expected_text",
    [
        # updating text in place
        ({"alt_text": None, "text": "some text"}, None, "some text"),
        ({"text": "some text"}, None, "some text"),
        # not updating either field is ok
        ({}, None, "DisplayName"),
        # swapping from text to alt text
        ({"alt_text": "some alt text", "text": None}, "some alt text", None),
    ],
)
def test_post_update_email_branding_allows_one_of_alt_text_or_text_whether_null_or_missing(
    admin_request,
    notify_db_session,
    data,
    expected_alt_text,
    expected_text,
):
    email_branding = create_email_branding(alt_text=None, text="DisplayName")
    admin_request.post(
        "email_branding.update_email_branding",
        email_branding_id=email_branding.id,
        _data=data,
        _expected_status=200,
    )

    email_branding = EmailBranding.query.one()
    assert email_branding.alt_text == expected_alt_text
    assert email_branding.text == expected_text


@pytest.mark.parametrize(
    "existing_data, data",
    [
        # try and set both
        ({"text": "existing text"}, {"alt_text": "new alt text"}),
        # try and remove both
        ({"text": "existing text"}, {"text": None}),
    ],
)
def test_post_update_email_branding_400s_if_not_one_of_alt_text_and_text(
    admin_request,
    notify_db_session,
    existing_data,
    data,
):
    email_branding = create_email_branding(**existing_data)
    response = admin_request.post(
        "email_branding.update_email_branding",
        email_branding_id=email_branding.id,
        _data=data,
        _expected_status=400,
    )
    assert response["message"] == "Email branding must have exactly one of alt_text and text."


def test_get_email_branding_name_for_alt_text_returns_alt_text_if_nothing_in_db_with_that_name(
    admin_request,
    notify_db_session,
):
    create_email_branding(name="Other Department")

    response = admin_request.post(
        "email_branding.get_email_branding_name_for_alt_text", _data={"alt_text": "Department Name"}
    )
    assert response == {"name": "Department Name"}


def test_get_email_branding_name_for_alt_text_returns_alternate_option_if_name_already_used(
    admin_request,
    notify_db_session,
):
    create_email_branding(name="DEPARTMENT name")

    response = admin_request.post(
        "email_branding.get_email_branding_name_for_alt_text", _data={"alt_text": "Department Name"}
    )
    assert response == {"name": "Department Name (alternate 1)"}


def test_get_email_branding_name_for_alt_text_returns_first_available_alternate_option(
    admin_request,
    notify_db_session,
):
    create_email_branding(name="Department Name")
    create_email_branding(name="Department Name (alternate 1)")
    create_email_branding(name="Department Name (alternate 2)")
    create_email_branding(name="Department Name (alternate 4)")
    # we've already renamed one of the options
    create_email_branding(name="Department Name (blue banner)")

    response = admin_request.post(
        "email_branding.get_email_branding_name_for_alt_text", _data={"alt_text": "Department Name"}
    )
    assert response == {"name": "Department Name (alternate 3)"}


def test_get_email_branding_name_for_alt_text_gives_up_if_100_options_assigned(
    admin_request,
    notify_db_session,
):
    create_email_branding(name="Department Name")
    for x in range(1, 100):
        create_email_branding(name=f"Department Name (alternate {x})")

    with pytest.raises(ValueError) as exc:
        admin_request.post("email_branding.get_email_branding_name_for_alt_text", _data={"alt_text": "Department Name"})
    assert "Couldnt assign a unique name for Department Name" in str(exc.value)


def test_get_orgs_and_services_associated_with_email_branding(admin_request, notify_db_session):
    email_branding = create_email_branding()

    orgs_and_services = admin_request.get(
        "email_branding.get_orgs_and_services_associated_with_email_branding",
        _expected_status=200,
        email_branding_id=email_branding.id,
    )["data"]

    assert orgs_and_services == {"services": [], "organisations": []}


def test_archive_email_branding_returns_400_if_branding_in_use(admin_request, notify_db_session):
    email_branding = create_email_branding()
    service_1 = create_service(service_name="service 1")
    service_1.email_branding = email_branding

    response = admin_request.post(
        "email_branding.archive_email_branding",
        email_branding_id=email_branding.id,
        _data=None,
        _expected_status=400,
    )

    assert response["message"] == "Email branding is in use and so it can't be archived."


def test_archive_email_branding_removes_branding_from_org_pools(admin_request, notify_db_session):
    email_branding_1 = create_email_branding(name="branding 1")
    email_branding_2 = create_email_branding(name="branding 2")

    org_1 = create_organisation(name="org 1")
    org_2 = create_organisation(name="org 2")

    dao_add_email_branding_list_to_organisation_pool(org_1.id, [email_branding_1.id])
    dao_add_email_branding_list_to_organisation_pool(org_2.id, [email_branding_1.id, email_branding_2.id])

    admin_request.post(
        "email_branding.archive_email_branding",
        email_branding_id=email_branding_1.id,
        _data=None,
        _expected_status=204,
    )

    assert len(dao_get_email_branding_pool_for_organisation(org_1.id)) == 0
    assert len(dao_get_email_branding_pool_for_organisation(org_2.id)) == 1


@freeze_time("2023-01-13")
def test_archive_email_branding_archives_branding_and_changes_its_name(admin_request, notify_db_session):
    email_branding_1 = create_email_branding(name="branding 1")

    admin_request.post(
        "email_branding.archive_email_branding",
        email_branding_id=email_branding_1.id,
        _data=None,
        _expected_status=204,
    )

    assert email_branding_1.active is False
    assert email_branding_1.name == "_archived_2023-01-13_branding 1"
