import datetime

import freezegun
import pytest

from app.models import BRANDING_ORG, EmailBranding
from tests.app.db import create_email_branding


def test_get_email_branding_options(admin_request, notify_db_session):
    email_branding1 = EmailBranding(colour="#FFFFFF", logo="/path/image.png", name="Org1")
    email_branding2 = EmailBranding(colour="#000000", logo="/path/other.png", name="Org2")
    notify_db_session.add_all([email_branding1, email_branding2])
    notify_db_session.commit()

    email_branding = admin_request.get("email_branding.get_email_branding_options")["email_branding"]

    assert len(email_branding) == 2
    assert {email_branding["id"] for email_branding in email_branding} == {
        str(email_branding1.id),
        str(email_branding2.id),
    }


def test_get_email_branding_by_id(admin_request, notify_db_session):
    email_branding = EmailBranding(colour="#FFFFFF", logo="/path/image.png", name="Some Org", text="My Org")
    notify_db_session.add(email_branding)
    notify_db_session.commit()

    response = admin_request.get(
        "email_branding.get_email_branding_by_id", _expected_status=200, email_branding_id=email_branding.id
    )

    assert set(response["email_branding"].keys()) == {"colour", "logo", "name", "id", "text", "brand_type", "alt_text"}
    assert response["email_branding"]["colour"] == "#FFFFFF"
    assert response["email_branding"]["logo"] == "/path/image.png"
    assert response["email_branding"]["name"] == "Some Org"
    assert response["email_branding"]["text"] == "My Org"
    assert response["email_branding"]["id"] == str(email_branding.id)
    assert response["email_branding"]["brand_type"] == str(email_branding.brand_type)
    assert response["email_branding"]["alt_text"] is None


@freezegun.freeze_time()
def test_post_create_email_branding(admin_request, notify_db_session):
    data = {
        "name": "test email_branding",
        "colour": "#0000ff",
        "logo": "/images/test_x2.png",
        "brand_type": BRANDING_ORG,
        "alt_text": None,
    }
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)
    assert data["name"] == response["data"]["name"]
    assert data["colour"] == response["data"]["colour"]
    assert data["logo"] == response["data"]["logo"]
    assert data["brand_type"] == response["data"]["brand_type"]
    assert response["data"]["text"] is None
    assert response["data"]["alt_text"] is None

    email_branding = EmailBranding.query.filter(EmailBranding.name == data["name"]).one()
    assert email_branding.created_by is None
    assert email_branding.created_at == datetime.datetime.utcnow()


@freezegun.freeze_time()
def test_post_create_email_branding_with_created_fields(admin_request, notify_db_session, sample_user):
    data = {
        "name": "test email_branding",
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
    assert email_branding.created_at == datetime.datetime.utcnow()
    assert email_branding.text is None


@freezegun.freeze_time()
def test_post_create_email_branding_adds_alt_text(admin_request, notify_db_session):
    data = {
        "name": "test email_branding",
        "alt_text": "foo",
    }
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)
    assert response["data"]["alt_text"] == "foo"

    email_branding = EmailBranding.query.one()
    assert email_branding.alt_text == "foo"


def test_post_create_email_branding_without_brand_type_defaults(admin_request, notify_db_session):
    data = {
        "name": "test email_branding",
        "colour": "#0000ff",
        "logo": "/images/test_x2.png",
    }
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)
    assert BRANDING_ORG == response["data"]["brand_type"]


def test_post_create_email_branding_without_logo_is_ok(admin_request, notify_db_session):
    data = {
        "name": "test email_branding",
        "colour": "#0000ff",
    }
    response = admin_request.post(
        "email_branding.create_email_branding",
        _data=data,
        _expected_status=201,
    )
    assert not response["data"]["logo"]


@pytest.mark.parametrize(
    "data, expected_text",
    [
        ({"logo": "images/text_x2.png", "name": "test branding"}, None),
        ({"logo": "images/text_x2.png", "name": "test branding", "text": None}, None),
        ({"logo": "images/text_x2.png", "name": "test branding", "text": ""}, ""),
        ({"logo": "images/text_x2.png", "name": "test branding", "text": "test text"}, "test text"),
    ],
)
def test_post_create_email_branding_colour_is_valid(admin_request, notify_db_session, data, expected_text):
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)

    assert response["data"]["logo"] == "images/text_x2.png"
    assert response["data"]["name"] == "test branding"
    assert response["data"]["colour"] is None
    assert response["data"]["text"] == expected_text


def test_post_create_email_branding_returns_400_when_name_is_missing(admin_request, notify_db_session):
    data = {"text": "some text", "logo": "images/text_x2.png"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=400)

    assert response["errors"][0]["message"] == "name is a required property"


@pytest.mark.parametrize(
    "data_update",
    [
        ({"name": "test email_branding 1"}),
        ({"logo": "images/text_x3.png", "colour": "#ffffff"}),
        ({"logo": "images/text_x3.png"}),
        ({"logo": "images/text_x3.png"}),
        ({"logo": "images/text_x3.png"}),
    ],
)
def test_post_update_email_branding_updates_field(admin_request, notify_db_session, data_update):
    data = {"name": "test email_branding", "logo": "images/text_x2.png"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)

    email_branding_id = response["data"]["id"]

    admin_request.post("email_branding.update_email_branding", _data=data_update, email_branding_id=email_branding_id)

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert str(email_branding[0].id) == email_branding_id
    for key in data_update.keys():
        assert getattr(email_branding[0], key) == data_update[key]
    # text field isn't updated
    assert email_branding[0].text is None


@freezegun.freeze_time(as_kwarg="frozen_time")
def test_post_update_email_branding_updated_fields(admin_request, notify_db_session, sample_user, **kwargs):
    frozen_time = kwargs["frozen_time"]
    start_time = frozen_time.time_to_freeze

    data = {"name": "test email_branding", "logo": "images/text_x2.png"}
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


@pytest.mark.parametrize(
    "data_update",
    [
        ({"text": "text email branding"}),
        ({"text": "new text", "name": "new name"}),
        ({"text": None, "name": "test name"}),
    ],
)
def test_post_update_email_branding_updates_field_with_text(admin_request, notify_db_session, data_update):
    data = {"name": "test email_branding", "logo": "images/text_x2.png"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=201)

    email_branding_id = response["data"]["id"]

    admin_request.post("email_branding.update_email_branding", _data=data_update, email_branding_id=email_branding_id)

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert str(email_branding[0].id) == email_branding_id
    for key in data_update.keys():
        assert getattr(email_branding[0], key) == data_update[key]


def test_create_email_branding_reject_invalid_brand_type(admin_request):
    data = {"name": "test email_branding", "brand_type": "NOT A TYPE"}
    response = admin_request.post("email_branding.create_email_branding", _data=data, _expected_status=400)

    assert response["errors"][0]["message"] == "brand_type NOT A TYPE is not one of [org, both, org_banner]"


def test_create_email_branding_400s_on_unique_violation(admin_request, notify_db_session):
    data = {"name": "test email_branding", "logo": "images/text_x2.png"}
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
