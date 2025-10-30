import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import call
from uuid import UUID

import pytest
from freezegun import freeze_time
from sqlalchemy import func, literal_column, select, table
from sqlalchemy.exc import IntegrityError

from app import signing
from app.constants import (
    EMAIL_TYPE,
    MOBILE_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_PENDING,
    NOTIFICATION_SENDING,
    NOTIFICATION_STATUS_LETTER_ACCEPTED,
    NOTIFICATION_STATUS_LETTER_RECEIVED,
    NOTIFICATION_STATUS_TYPES_FAILED,
    NOTIFICATION_TECHNICAL_FAILURE,
    PRECOMPILED_TEMPLATE_NAME,
    SMS_TYPE,
)
from app.dao.services_dao import dao_add_user_to_service
from app.models import (
    AnnualBilling,
    ApiKey,
    EmailBranding,
    FactBilling,
    FactNotificationStatus,
    InboundNumber,
    InboundSms,
    InboundSmsHistory,
    InvitedOrganisationUser,
    InvitedUser,
    Job,
    LetterBranding,
    LetterCostThreshold,
    Notification,
    NotificationHistory,
    Organisation,
    Permission,
    ReportRequest,
    SerializedAnnualBilling,
    SerializedFreeSmsItems,
    SerializedInboundNumber,
    SerializedOrganisation,
    SerializedOrganisationForList,
    SerializedServiceOrgDashboard,
    SerializedServiceSmsSender,
    Service,
    ServiceGuestList,
    ServiceSmsSender,
    Template,
    TemplateFolder,
    TemplateHistory,
    UnsubscribeRequest,
    UnsubscribeRequestHistory,
    User,
)
from app.utils import DATETIME_FORMAT
from tests.app.db import (
    create_inbound_number,
    create_letter_contact,
    create_letter_rate,
    create_notification,
    create_reply_to_email,
    create_service,
    create_template,
    create_template_folder,
)


@pytest.mark.parametrize("mobile_number", ["07700 900678", "+44 7700 900678"])
def test_should_build_service_guest_list_from_mobile_number(mobile_number):
    service_guest_list = ServiceGuestList.from_string("service_id", MOBILE_TYPE, mobile_number)

    assert service_guest_list.recipient == mobile_number


@pytest.mark.parametrize("email_address", ["test@example.com"])
def test_should_build_service_guest_list_from_email_address(email_address):
    service_guest_list = ServiceGuestList.from_string("service_id", EMAIL_TYPE, email_address)

    assert service_guest_list.recipient == email_address


@pytest.mark.parametrize(
    "contact, recipient_type", [("", None), ("07700dsadsad", MOBILE_TYPE), ("gmail.com", EMAIL_TYPE)]
)
def test_should_not_build_service_guest_list_from_invalid_contact(recipient_type, contact):
    with pytest.raises(ValueError):
        ServiceGuestList.from_string("service_id", recipient_type, contact)


@pytest.mark.parametrize(
    "initial_statuses, expected_statuses",
    [
        # passing in single statuses as strings
        (NOTIFICATION_FAILED, NOTIFICATION_STATUS_TYPES_FAILED),
        (NOTIFICATION_STATUS_LETTER_ACCEPTED, [NOTIFICATION_SENDING, NOTIFICATION_CREATED]),
        (NOTIFICATION_CREATED, [NOTIFICATION_CREATED]),
        (NOTIFICATION_TECHNICAL_FAILURE, [NOTIFICATION_TECHNICAL_FAILURE]),
        # passing in lists containing single statuses
        ([NOTIFICATION_FAILED], NOTIFICATION_STATUS_TYPES_FAILED),
        ([NOTIFICATION_CREATED], [NOTIFICATION_CREATED]),
        ([NOTIFICATION_TECHNICAL_FAILURE], [NOTIFICATION_TECHNICAL_FAILURE]),
        (NOTIFICATION_STATUS_LETTER_RECEIVED, [NOTIFICATION_DELIVERED]),
        # passing in lists containing multiple statuses
        ([NOTIFICATION_FAILED, NOTIFICATION_CREATED], NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_CREATED]),
        ([NOTIFICATION_CREATED, NOTIFICATION_PENDING], [NOTIFICATION_CREATED, NOTIFICATION_PENDING]),
        (
            [NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE],
            [NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE],
        ),
        (
            [NOTIFICATION_FAILED, NOTIFICATION_STATUS_LETTER_ACCEPTED],
            NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_SENDING, NOTIFICATION_CREATED],
        ),
        # checking we don't end up with duplicates
        (
            [NOTIFICATION_FAILED, NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE],
            NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_CREATED],
        ),
    ],
)
def test_status_conversion(initial_statuses, expected_statuses):
    converted_statuses = Notification.substitute_status(initial_statuses)
    assert len(converted_statuses) == len(expected_statuses)
    assert set(converted_statuses) == set(expected_statuses)


@freeze_time("2016-01-01 11:09:00.000000")
@pytest.mark.parametrize(
    "template_type, recipient",
    [
        ("sms", "+447700900855"),
        ("email", "foo@bar.com"),
    ],
)
def test_notification_for_csv_returns_correct_type(sample_service, template_type, recipient):
    template = create_template(sample_service, template_type=template_type)
    notification = create_notification(template, to_field=recipient)

    serialized = notification.serialize_for_csv()
    assert serialized["template_type"] == template_type


@freeze_time("2016-01-01 11:09:00.000000")
def test_notification_for_csv_returns_correct_job_row_number(sample_job):
    notification = create_notification(sample_job.template, sample_job, job_row_number=0)

    serialized = notification.serialize_for_csv()
    assert serialized["row_number"] == 1


@freeze_time("2016-01-30 12:39:58.321312")
@pytest.mark.parametrize(
    "template_type, status, expected_status",
    [
        ("email", "failed", "Failed"),
        ("email", "technical-failure", "Technical failure"),
        ("email", "temporary-failure", "Inbox not accepting messages right now"),
        ("email", "permanent-failure", "Email address doesn’t exist"),
        ("sms", "temporary-failure", "Phone not accepting messages right now"),
        ("sms", "permanent-failure", "Phone number doesn’t exist"),
        ("sms", "sent", "Sent internationally"),
        ("letter", "created", "Accepted"),
        ("letter", "sending", "Accepted"),
        ("letter", "technical-failure", "Technical failure"),
        ("letter", "permanent-failure", "Permanent failure"),
        ("letter", "delivered", "Received"),
    ],
)
def test_notification_for_csv_returns_formatted_status(sample_service, template_type, status, expected_status):
    template = create_template(sample_service, template_type=template_type)
    notification = create_notification(template, status=status)

    serialized = notification.serialize_for_csv()
    assert serialized["status"] == expected_status


@freeze_time("2017-03-26 23:01:53.321312")
def test_notification_for_csv_returns_bst_correctly(sample_template):
    notification = create_notification(sample_template)

    serialized = notification.serialize_for_csv()
    assert serialized["created_at"] == "2017-03-27 00:01:53"


def test_notification_personalisation_getter_returns_empty_dict_from_None():
    noti = Notification()
    noti._personalisation = None
    assert noti.personalisation == {}


def test_notification_personalisation_getter_always_returns_empty_dict():
    noti = Notification()
    noti._personalisation = signing.encode({})
    assert noti.personalisation == {}


@pytest.mark.parametrize("input_value", [None, {}])
def test_notification_personalisation_setter_always_sets_empty_dict(input_value):
    noti = Notification()
    noti.personalisation = input_value

    assert noti._personalisation == signing.encode({})


def test_notification_subject_is_none_for_sms(sample_service):
    template = create_template(service=sample_service, template_type=SMS_TYPE)
    notification = create_notification(template=template)
    assert notification.subject is None


@pytest.mark.parametrize("template_type", ["email", "letter"])
def test_notification_subject_fills_in_placeholders(sample_service, template_type):
    template = create_template(service=sample_service, template_type=template_type, subject="((name))")
    notification = create_notification(template=template, personalisation={"name": "hello"})
    assert notification.subject == "hello"


def test_letter_notification_serializes_with_address(client, sample_letter_notification):
    sample_letter_notification.personalisation = {
        "address_line_1": "foo",
        "address_line_3": "bar",
        "address_line_5": None,
        "postcode": "SW1 1AA",
    }
    res = sample_letter_notification.serialize()
    assert res["line_1"] == "foo"
    assert res["line_2"] is None
    assert res["line_3"] == "bar"
    assert res["line_4"] is None
    assert res["line_5"] is None
    assert res["line_6"] is None
    assert res["postcode"] == "SW1 1AA"


def test_notification_serializes_created_by_name_with_no_created_by_id(client, sample_notification):
    res = sample_notification.serialize()
    assert res["created_by_name"] is None


def test_notification_serializes_created_by_name_with_created_by_id(client, sample_notification, sample_user):
    sample_notification.created_by_id = sample_user.id
    res = sample_notification.serialize()
    assert res["created_by_name"] == sample_user.name


def test_sms_notification_serializes_without_subject(client, sample_template):
    res = sample_template.serialize_for_v2()
    assert res["subject"] is None


def test_email_notification_serializes_with_subject(client, sample_email_template):
    res = sample_email_template.serialize_for_v2()
    assert res["subject"] == "Email Subject"


def test_letter_notification_serializes_with_subject(client, sample_letter_template):
    res = sample_letter_template.serialize_for_v2()
    assert res["subject"] == "Template subject"


def test_notification_serialize_with_cost_data_for_sms(client, sample_template, sms_rate):
    notification = create_notification(sample_template, billable_units=2)

    response = notification.serialize_with_cost_data()

    assert response["is_cost_data_ready"] is True
    assert response["cost_details"] == {
        "billable_sms_fragments": 2,
        "international_rate_multiplier": 1.0,
        "sms_rate": 0.0227,
    }
    assert response["cost_in_pounds"] == 0.0454


@pytest.mark.parametrize("status", ["created", "sending", "delivered", "returned-letter"])
def test_notification_serialize_with_cost_data_for_letter(client, sample_letter_template, letter_rate, status):
    notification = create_notification(sample_letter_template, billable_units=1, postage="second", status=status)

    response = notification.serialize_with_cost_data()

    assert response["is_cost_data_ready"] is True
    assert response["cost_details"] == {"billable_sheets_of_paper": 1, "postage": "second"}
    assert response["cost_in_pounds"] == 0.54


@freeze_time("2024-07-10 12:11:04.000000")
def test_notification_serialize_with_cost_data_uses_cache_to_get_sms_rate(client, mocker, sample_template, sms_rate):
    notification_1 = create_notification(sample_template, billable_units=1)
    notification_2 = create_notification(sample_template, billable_units=2)

    mock_get_sms_rate = mocker.patch("app.dao.sms_rate_dao.dao_get_sms_rate_for_timestamp", return_value=sms_rate)
    mock_redis_get = mocker.patch(
        "app.RedisClient.get",
        side_effect=[None, b"0.0227"],
    )
    mock_redis_set = mocker.patch(
        "app.RedisClient.set",
    )

    # we serialize twice
    notification_1.serialize_with_cost_data()
    response = notification_2.serialize_with_cost_data()

    # redis is called
    assert mock_redis_get.call_args_list == [
        call("sms-rate-for-2024-07-10"),
        call("sms-rate-for-2024-07-10"),
    ]
    assert mock_redis_set.call_args_list == [call("sms-rate-for-2024-07-10", 0.0227, ex=86400)]

    # but we only get rate once
    assert mock_get_sms_rate.call_args_list == [
        call(datetime.now().date()),
    ]

    # check that response returned from cache looks right
    assert response["cost_details"] == {
        "billable_sms_fragments": 2,
        "international_rate_multiplier": 1.0,
        "sms_rate": 0.0227,
    }
    assert response["cost_in_pounds"] == 0.0454


@freeze_time("2024-07-10 12:11:04.000000")
def test_notification_serialize_with_cost_data_uses_cache_to_get_letter_rate(
    client, mocker, sample_letter_template, letter_rate, notify_db_session
):
    # letter rate for 2 sheets of paper
    other_rate = create_letter_rate(
        start_date=datetime.now(UTC) - timedelta(days=1), rate=0.85, post_class="first", sheet_count=2
    )
    # economy rate for 1 sheet of paper
    economy_rate = create_letter_rate(
        start_date=datetime.now(UTC) - timedelta(days=1), rate=0.59, post_class="economy", sheet_count=1
    )
    # two letters that are 1 sheet of paper each 2nd class,
    # one letter that is two sheets long 1st class
    # and one letter that is 1 sheet of paper economy class
    notification_1 = create_notification(sample_letter_template, billable_units=1, postage="second")
    notification_2 = create_notification(sample_letter_template, billable_units=1, postage="second")
    notification_3 = create_notification(sample_letter_template, billable_units=2, postage="first")
    notification_4 = create_notification(sample_letter_template, billable_units=1, postage="economy")

    mock_get_letter_rates = mocker.patch(
        "app.dao.letter_rate_dao.dao_get_letter_rates_for_timestamp",
        side_effect=[[letter_rate, other_rate], [letter_rate, other_rate], [economy_rate, letter_rate]],
    )
    mock_redis_get = mocker.patch(
        "app.RedisClient.get",
        side_effect=[None, b"0.54", None, None],
    )
    mock_redis_set = mocker.patch(
        "app.RedisClient.set",
    )

    # we serialize four times - two times for one rate, and twice for the following rates
    notification_1.serialize_with_cost_data()
    response = notification_2.serialize_with_cost_data()
    notification_3.serialize_with_cost_data()
    notification_4.serialize_with_cost_data()

    # redis is called
    assert mock_redis_get.call_args_list == [
        call("letter-rate-for-date-2024-07-10-sheets-1-postage-second"),
        call("letter-rate-for-date-2024-07-10-sheets-1-postage-second"),
        call("letter-rate-for-date-2024-07-10-sheets-2-postage-first"),
        call("letter-rate-for-date-2024-07-10-sheets-1-postage-economy"),
    ]
    assert mock_redis_set.call_args_list == [
        call("letter-rate-for-date-2024-07-10-sheets-1-postage-second", 0.54, ex=86400),
        call("letter-rate-for-date-2024-07-10-sheets-2-postage-first", 0.85, ex=86400),
        call("letter-rate-for-date-2024-07-10-sheets-1-postage-economy", 0.59, ex=86400),
    ]

    # but we only get each rate once from db
    assert mock_get_letter_rates.call_args_list == [
        call(datetime.now().date()),
        call(datetime.now().date()),
        call(datetime.now().date()),
    ]

    # check that response returned from cache looks right
    assert response["cost_in_pounds"] == 0.54


def test_notification_serialize_with_cost_data_for_sms_when_data_not_ready(client, sample_template, letter_rate):
    notification = create_notification(sample_template, billable_units=None, postage="first", status="created")

    response = notification.serialize_with_cost_data()

    assert response["is_cost_data_ready"] is False
    assert response["cost_details"] == {}
    assert response["cost_in_pounds"] is None


@pytest.mark.parametrize("status", ["created", "pending-virus-check"])
def test_notification_serialize_with_cost_data_for_letter_when_data_not_ready(
    client, sample_letter_template, letter_rate, status
):
    notification = create_notification(sample_letter_template, billable_units=None, postage="first", status=status)

    response = notification.serialize_with_cost_data()

    assert response["is_cost_data_ready"] is False
    assert response["cost_details"] == {}
    assert response["cost_in_pounds"] is None


@pytest.mark.parametrize("status", ["validation-failed", "technical-failure", "cancelled", "virus-scan-failed"])
def test_notification_serialize_with_with_cost_data_for_letter_that_wasnt_sent(
    client, sample_letter_template, letter_rate, status
):
    notification = create_notification(sample_letter_template, billable_units=1, postage="first", status=status)

    response = notification.serialize_with_cost_data()

    assert response["is_cost_data_ready"] is True
    assert response["cost_details"] == {"billable_sheets_of_paper": 0, "postage": "first"}
    assert response["cost_in_pounds"] == 0.00


def test_notification_serialize_with_cost_data_for_email(client, sample_email_template):
    notification = create_notification(sample_email_template, billable_units=0)

    response = notification.serialize_with_cost_data()

    assert response["cost_details"] == {}
    assert response["cost_in_pounds"] == 0.00


def test_notification_references_template_history(client, sample_template):
    noti = create_notification(sample_template)
    sample_template.version = 3
    sample_template.content = "New template content"

    res = noti.serialize()
    assert res["template"]["version"] == 1

    assert res["body"] == noti.template.content
    assert noti.template.content != sample_template.content


@pytest.mark.parametrize(
    "model",
    (
        ApiKey,
        FactBilling,
        FactNotificationStatus,
        InboundSms,
        InboundSmsHistory,
        InvitedOrganisationUser,
        InvitedUser,
        Job,
        Notification,
        NotificationHistory,
        Permission,
        ReportRequest,
        Template,
        TemplateFolder,
        TemplateHistory,
        UnsubscribeRequest,
        UnsubscribeRequestHistory,
    ),
)
def test_extended_statistics_presence(notify_db_session, model):
    """
    Test that the extended statistics objects in the fully-migrated database correspond to
    those declared on a model's  __extended_statistics__
    """

    # a map of internal statistics kind labels to those used in the
    # CREATE STATISTICS syntax
    kinds_map = {
        "d": "ndistinct",
        "f": "dependencies",
        "m": "mcv",
    }

    # it would be much more convenient to use the pg_stats_ext view, but
    # that doesn't show entries for empty tables with no statistics - which
    # is how tables tend to appear in these tests - so we have to do a lot
    # of the joining nonsense ourselves.
    # NOTE not handled: expression statistics
    assert frozenset(
        (
            (name, frozenset(attnames), frozenset(kinds_map[kind] for kind in kinds))
            for name, attnames, kinds in notify_db_session.execute(
                select(
                    literal_column("stxname"),
                    select(func.array_agg(literal_column("attname")))
                    .select_from(table("pg_attribute"))
                    .where(
                        literal_column("pg_attribute.attrelid") == literal_column("pg_statistic_ext.stxrelid"),
                        literal_column("pg_attribute.attnum") == literal_column("pg_statistic_ext.stxkeys").any_(),
                    )
                    .scalar_subquery(),
                    literal_column("stxkind"),
                )
                .select_from(
                    table("pg_statistic_ext"),
                    table("pg_class"),
                )
                .where(
                    literal_column("pg_class.oid") == literal_column("pg_statistic_ext.stxrelid"),
                    literal_column("pg_class.relname") == model.__tablename__,
                )
            ).fetchall()
        )
    ) == frozenset(
        ((name, frozenset(attnames), frozenset(kinds)) for name, attnames, kinds in model.__extended_statistics__)
    )


def test_notification_requires_a_valid_template_version(client, sample_template):
    sample_template.version = 2
    with pytest.raises(IntegrityError):
        create_notification(sample_template)


def test_inbound_number_serializes_with_service(client, notify_db_session):
    service = create_service()
    inbound_number = create_inbound_number(number="1", service_id=service.id)
    serialized_inbound_number = inbound_number.serialize()
    assert serialized_inbound_number.get("id") == str(inbound_number.id)
    assert serialized_inbound_number.get("service").get("id") == str(inbound_number.service.id)
    assert serialized_inbound_number.get("service").get("name") == inbound_number.service.name


def test_inbound_number_returns_inbound_number(client, notify_db_session):
    service = create_service()
    inbound_number = create_inbound_number(number="1", service_id=service.id)

    assert service.get_inbound_number() == inbound_number.number


def test_inbound_number_returns_none_when_no_inbound_number(client, notify_db_session):
    service = create_service()

    assert not service.get_inbound_number()


def test_service_get_default_reply_to_email_address(sample_service):
    create_reply_to_email(service=sample_service, email_address="default@email.com")

    assert sample_service.get_default_reply_to_email_address() == "default@email.com"


def test_service_get_default_contact_letter(sample_service):
    create_letter_contact(service=sample_service, contact_block="London,\nNW1A 1AA")

    assert sample_service.get_default_letter_contact() == "London,\nNW1A 1AA"


def test_service_get_default_sms_sender(notify_db_session):
    service = create_service()
    assert service.get_default_sms_sender() == "testing"


def test_letter_notification_serializes_correctly(client, sample_letter_notification):
    sample_letter_notification.personalisation = {
        "addressline1": "test",
        "addressline2": "London",
        "postcode": "N1",
    }

    json = sample_letter_notification.serialize()
    assert json["line_1"] == "test"
    assert json["line_2"] == "London"
    assert json["postcode"] == "N1"


def test_letter_notification_postcode_can_be_null_for_precompiled_letters(client, sample_letter_notification):
    sample_letter_notification.personalisation = {
        "address_line_1": "test",
        "address_line_2": "London",
    }

    json = sample_letter_notification.serialize()
    assert json["line_1"] == "test"
    assert json["line_2"] == "London"
    assert json["postcode"] is None


def test_is_precompiled_letter_false(sample_letter_template):
    assert not sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_true(sample_letter_template):
    sample_letter_template.hidden = True
    sample_letter_template.name = PRECOMPILED_TEMPLATE_NAME
    assert sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_hidden_true_not_name(sample_letter_template):
    sample_letter_template.hidden = True
    assert not sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_name_correct_not_hidden(sample_letter_template):
    sample_letter_template.name = PRECOMPILED_TEMPLATE_NAME
    assert not sample_letter_template.is_precompiled_letter


def test_template_folder_is_parent(sample_service):
    x = None
    folders = []
    for i in range(5):
        x = create_template_folder(sample_service, name=str(i), parent=x)
        folders.append(x)

    assert folders[0].is_parent_of(folders[1])
    assert folders[0].is_parent_of(folders[2])
    assert folders[0].is_parent_of(folders[4])
    assert folders[1].is_parent_of(folders[2])
    assert not folders[1].is_parent_of(folders[0])


@pytest.mark.parametrize("is_platform_admin", (False, True))
def test_user_can_use_webauthn_if_platform_admin(sample_user, is_platform_admin):
    sample_user.platform_admin = is_platform_admin
    assert sample_user.can_use_webauthn == is_platform_admin


@pytest.mark.parametrize(
    ("auth_type", "can_use_webauthn"), [("email_auth", False), ("sms_auth", False), ("webauthn_auth", True)]
)
def test_user_can_use_webauthn_if_they_login_with_it(sample_user, auth_type, can_use_webauthn):
    sample_user.auth_type = auth_type
    assert sample_user.can_use_webauthn == can_use_webauthn


def test_user_can_use_webauthn_if_in_notify_team(notify_service):
    assert notify_service.users[0].can_use_webauthn


def test_letter_cost_threshold_is_json_serializable():
    assert json.dumps(LetterCostThreshold.sorted) == '"sorted"'


@pytest.mark.parametrize(
    "service_filter_keys, expected_keys",
    [
        (None, None),  # Default to ID only
        (["id"], ["id"]),  # Explicitly passing "id" creates a list of dictionaries
        (["name"], ["id", "name"]),
        (["created_at"], ["id", "created_at"]),
        (["name", "created_at", "organisation_id"], ["id", "name", "created_at", "organisation_id"]),
    ],
)
def test_serialize_service_filter_keys(
    notify_db_session, sample_service, sample_user, service_filter_keys, expected_keys
):
    dao_add_user_to_service(sample_service, sample_user)
    serialized_data = sample_user.serialize(service_filter_keys=service_filter_keys)

    assert "services" in serialized_data

    if service_filter_keys is None:
        # If None is passed, expect a flat list of IDs
        assert isinstance(serialized_data["services"], list)
        assert all(isinstance(service_id, UUID) for service_id in serialized_data["services"])
    else:
        # Otherwise, expect a list of dictionaries
        for service in serialized_data["services"]:
            assert set(service.keys()) == set(expected_keys)


def test_email_branding_serializes_with_all_fields(notify_db_session):
    user_id = uuid.uuid4()
    created_at = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    updated_at = datetime(2025, 1, 2, 12, 0, tzinfo=UTC)

    email_branding = EmailBranding(
        id=uuid.uuid4(),
        colour="#000000",
        logo="logo.png",
        name="Test Brand",
        text="Test Text",
        brand_type="org",
        alt_text=None,  # Since we have text, alt_text must be None due to constraint
        created_by=user_id,
        created_at=created_at,
        updated_at=updated_at,
    )

    serialized = email_branding.serialize()

    assert serialized.id == str(email_branding.id)
    assert serialized.colour == "#000000"
    assert serialized.logo == "logo.png"
    assert serialized.name == "Test Brand"
    assert serialized.text == "Test Text"
    assert serialized.brand_type == "org"
    assert serialized.alt_text is None
    assert serialized.created_by == user_id
    assert serialized.created_at == created_at.strftime("%Y-%m-%d %H:%M:%S.%f")
    assert serialized.updated_at == updated_at.strftime("%Y-%m-%d %H:%M:%S.%f")


def test_email_branding_serializes_with_minimal_fields(notify_db_session):
    email_branding = EmailBranding(
        id=uuid.uuid4(),
        name="Test Brand",
        brand_type="org",
        alt_text="Alt Text",  # Using alt_text instead of text
    )

    serialized = email_branding.serialize()

    assert serialized.id == str(email_branding.id)
    assert serialized.name == "Test Brand"
    assert serialized.brand_type == "org"
    assert serialized.alt_text == "Alt Text"
    assert serialized.text is None
    assert serialized.colour is None
    assert serialized.logo is None
    assert serialized.created_by is None
    assert serialized.created_at is None
    assert serialized.updated_at is None


def test_email_branding_serialization_only_returns_defined_fields(notify_db_session):
    email_branding = EmailBranding(
        id=uuid.uuid4(),
        name="Test Brand",
        brand_type="org",
        fake_field="Should not be serialized",  # This field does not exist in the model
    )

    serialized = email_branding.serialize()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__dataclass_fields__.keys()) == {
        "id",
        "colour",
        "logo",
        "name",
        "text",
        "brand_type",
        "alt_text",
        "created_by",
        "created_at",
        "updated_at",
    }

    assert not hasattr(serialized, "fake_field")


def test_letter_branding_serializes_with_all_fields(notify_db_session):
    user_id = uuid.uuid4()
    created_at = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    updated_at = datetime(2025, 1, 2, 12, 0, tzinfo=UTC)

    letter_branding = LetterBranding(
        id=uuid.uuid4(),
        name="Test Brand",
        filename="test-brand.svg",
        created_by_id=user_id,
        created_at=created_at,
        updated_at=updated_at,
    )

    serialized = letter_branding.serialize()

    assert serialized.id == str(letter_branding.id)
    assert serialized.name == "Test Brand"
    assert serialized.filename == "test-brand.svg"
    assert serialized.created_by == str(user_id)
    assert serialized.created_at == created_at.strftime("%Y-%m-%d %H:%M:%S.%f")
    assert serialized.updated_at == updated_at.strftime("%Y-%m-%d %H:%M:%S.%f")


def test_letter_branding_serializes_with_minimal_fields(notify_db_session):
    letter_branding = LetterBranding(id=uuid.uuid4(), name="Test Brand", filename="test-brand.svg")

    serialized = letter_branding.serialize()

    assert serialized.id == str(letter_branding.id)
    assert serialized.name == "Test Brand"
    assert serialized.filename == "test-brand.svg"
    assert serialized.created_by is None
    assert serialized.created_at is None
    assert serialized.updated_at is None


def test_letter_branding_serialization_only_returns_defined_fields(notify_db_session):
    letter_branding = LetterBranding(
        id=uuid.uuid4(), name="Test Brand", filename="test-brand.svg", fake_field="Should not be serialized"
    )

    serialized = letter_branding.serialize()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__dataclass_fields__.keys()) == {
        "id",
        "name",
        "filename",
        "created_by",
        "created_at",
        "updated_at",
    }

    assert not hasattr(serialized, "fake_field")


def test_organisation_serializes_with_all_fields(notify_db_session):
    user = User(id=uuid.uuid4(), name="Test User", email_address="test@example.com", password="password")
    notify_db_session.add(user)

    org = Organisation(
        id=uuid.uuid4(),
        name="Test Organisation",
        active=True,
        crown=True,
        organisation_type="central",
        letter_branding_id=uuid.uuid4(),
        email_branding_id=uuid.uuid4(),
        agreement_signed=True,
        agreement_signed_at=datetime(2023, 1, 1, tzinfo=UTC),
        agreement_signed_by_id=user.id,
        agreement_signed_on_behalf_of_name="On Behalf",
        agreement_signed_on_behalf_of_email_address="behalf@example.com",
        agreement_signed_version=1.0,
        request_to_go_live_notes="Ready to go live",
        can_approve_own_go_live_requests=True,
        notes="Some notes",
        purchase_order_number="PO123",
        billing_contact_names="Contact Name",
        billing_contact_email_addresses="billing@example.com",
        billing_reference="REF123",
    )
    notify_db_session.add(org)
    notify_db_session.commit()

    result = org.serialize()
    assert isinstance(result, SerializedOrganisation)

    assert result.id == str(org.id)
    assert result.name == "Test Organisation"
    assert result.active is True
    assert result.crown is True
    assert result.organisation_type == "central"
    assert result.letter_branding_id == str(org.letter_branding_id)
    assert result.email_branding_id == str(org.email_branding_id)
    assert result.agreement_signed is True
    assert result.agreement_signed_at == datetime(2023, 1, 1, tzinfo=UTC)
    assert result.agreement_signed_by_id == str(user.id)
    assert result.agreement_signed_on_behalf_of_name == "On Behalf"
    assert result.agreement_signed_on_behalf_of_email_address == "behalf@example.com"
    assert result.agreement_signed_version == 1.0
    assert result.domains == []
    assert result.request_to_go_live_notes == "Ready to go live"
    assert result.count_of_live_services == 0
    assert result.notes == "Some notes"
    assert result.purchase_order_number == "PO123"
    assert result.billing_contact_names == "Contact Name"
    assert result.billing_contact_email_addresses == "billing@example.com"
    assert result.billing_reference == "REF123"
    assert result.can_approve_own_go_live_requests is True
    assert result.permissions == []


def test_organisation_serializes_with_minimal_fields(notify_db_session):
    org = Organisation(
        id=uuid.uuid4(),
        name="Test Organisation",
        active=True,
        can_approve_own_go_live_requests=False,
    )
    notify_db_session.add(org)
    notify_db_session.commit()

    result = org.serialize()

    assert result.id == str(org.id)
    assert result.name == "Test Organisation"
    assert result.active is True
    assert result.crown is None
    assert result.organisation_type is None
    assert result.letter_branding_id is None
    assert result.email_branding_id is None
    assert result.agreement_signed is None
    assert result.agreement_signed_at is None
    assert result.agreement_signed_by_id is None
    assert result.agreement_signed_on_behalf_of_name is None
    assert result.agreement_signed_on_behalf_of_email_address is None
    assert result.agreement_signed_version is None
    assert result.domains == []
    assert result.request_to_go_live_notes is None
    assert result.count_of_live_services == 0
    assert result.notes is None
    assert result.purchase_order_number is None
    assert result.billing_contact_names is None
    assert result.billing_contact_email_addresses is None
    assert result.billing_reference is None
    assert result.can_approve_own_go_live_requests is False
    assert result.permissions == []


def test_organisation_serialization_only_returns_defined_fields(notify_db_session):
    """Test to ensure we only get fields that are defined in the serialization dataclass"""
    org = Organisation(
        id=uuid.uuid4(),
        name="Test Organisation",
        active=True,
        can_approve_own_go_live_requests=True,
        fake_field="Should not be serialized",
    )
    notify_db_session.add(org)
    notify_db_session.commit()

    serialized = org.serialize()

    # Should only contain fields defined in SerializedOrganisation dataclass
    assert set(serialized.__annotations__.keys()) == {
        "id",
        "name",
        "active",
        "crown",
        "organisation_type",
        "letter_branding_id",
        "email_branding_id",
        "agreement_signed",
        "agreement_signed_at",
        "agreement_signed_by_id",
        "agreement_signed_on_behalf_of_name",
        "agreement_signed_on_behalf_of_email_address",
        "agreement_signed_version",
        "domains",
        "request_to_go_live_notes",
        "count_of_live_services",
        "notes",
        "purchase_order_number",
        "billing_contact_names",
        "billing_contact_email_addresses",
        "billing_reference",
        "can_approve_own_go_live_requests",
        "permissions",
    }

    assert not hasattr(serialized, "fake_field")


def test_organisation_serializes_for_list(notify_db_session):
    """Test the list serialization of an organisation"""
    org = Organisation(
        id=uuid.uuid4(),
        name="Test Organisation",
        active=True,
        organisation_type="central",
    )
    notify_db_session.add(org)
    notify_db_session.commit()

    result = org.serialize_for_list()
    assert isinstance(result, SerializedOrganisationForList)

    assert result.name == "Test Organisation"
    assert result.id == str(org.id)
    assert result.active is True
    assert result.count_of_live_services == 0
    assert result.domains == []
    assert result.organisation_type == "central"


def test_organisation_serialization_for_list_only_returns_defined_fields(notify_db_session):
    """Test to ensure we only get fields that are defined in the SerializedOrganisationForList dataclass"""
    org = Organisation(id=uuid.uuid4(), name="Test Organisation", active=True, fake_field="Should not be serialized")
    notify_db_session.add(org)
    notify_db_session.commit()

    result = org.serialize_for_list()

    # Should only contain fields defined in SerializedOrganisationForList dataclass
    assert set(result.__annotations__.keys()) == {
        "name",
        "id",
        "active",
        "count_of_live_services",
        "domains",
        "organisation_type",
    }
    assert not hasattr(result, "fake_field")


def test_annual_billing_serialize_free_sms_items(notify_db_session):
    """Test the free SMS items serialization of annual billing"""
    service = Service(name="Test Service")
    notify_db_session.add(service)

    annual_billing = AnnualBilling(service=service, free_sms_fragment_limit=250000, financial_year_start=2022)
    notify_db_session.add(annual_billing)
    notify_db_session.commit()

    result = annual_billing.serialize_free_sms_items()

    assert isinstance(result, SerializedFreeSmsItems)
    assert result.free_sms_fragment_limit == 250000
    assert result.financial_year_start == 2022


def test_annual_billing_serialize_free_sms_items_only_returns_defined_fields(notify_db_session):
    """Test to ensure we only get fields that are defined in the SerializedFreeSmsItems dataclass"""
    service = Service(name="Test Service")
    notify_db_session.add(service)

    annual_billing = AnnualBilling(
        service=service,
        free_sms_fragment_limit=250000,
        financial_year_start=2022,
        fake_field="Should not be serialized",
    )
    notify_db_session.add(annual_billing)
    notify_db_session.commit()

    result = annual_billing.serialize_free_sms_items()

    # Should only contain fields defined in SerializedFreeSmsItems dataclass
    assert set(result.__annotations__.keys()) == {"free_sms_fragment_limit", "financial_year_start"}
    assert not hasattr(result, "fake_field")


def test_annual_billing_serialize(notify_db_session):
    """Test the full serialization of annual billing"""
    service = Service(name="Test Service")
    notify_db_session.add(service)

    now = datetime.now(UTC)
    annual_billing = AnnualBilling(
        service=service,
        free_sms_fragment_limit=250000,
        financial_year_start=2022,
        created_at=now,
        updated_at=now + timedelta(days=1),
    )
    notify_db_session.add(annual_billing)
    notify_db_session.commit()

    result = annual_billing.serialize()

    assert isinstance(result, SerializedAnnualBilling)
    assert result.id == str(annual_billing.id)
    assert result.free_sms_fragment_limit == 250000
    assert result.service_id == str(service.id)
    assert result.financial_year_start == 2022
    assert result.created_at == now.strftime(DATETIME_FORMAT)
    assert result.updated_at == (now + timedelta(days=1)).strftime(DATETIME_FORMAT)
    assert result.service == {"id": str(service.id), "name": "Test Service"}


def test_annual_billing_serialize_with_no_service(notify_db_session):
    """Test serialization of annual billing when service is not loaded"""
    now = datetime.now(UTC)
    annual_billing = AnnualBilling(
        service_id=uuid.uuid4(), free_sms_fragment_limit=250000, financial_year_start=2022, created_at=now
    )
    notify_db_session.add(annual_billing)
    notify_db_session.commit()

    result = annual_billing.serialize()

    assert isinstance(result, SerializedAnnualBilling)
    assert result.service is None


def test_annual_billing_serialization_only_returns_defined_fields(notify_db_session):
    """Test to ensure we only get fields that are defined in the serialization dataclass"""
    service = Service(name="Test Service")
    notify_db_session.add(service)
    annual_billing = AnnualBilling(
        service=service,
        free_sms_fragment_limit=250000,
        financial_year_start=2022,
        fake_field="Should not be serialized",
    )
    notify_db_session.add(annual_billing)
    notify_db_session.commit()
    serialized = annual_billing.serialize()

    # Should only contain fields defined in SerializedAnnualBilling dataclass
    assert set(serialized.__annotations__.keys()) == {
        "id",
        "free_sms_fragment_limit",
        "service_id",
        "financial_year_start",
        "created_at",
        "updated_at",
        "service",
    }
    assert not hasattr(serialized, "fake_field")


def test_inbound_number_serializes_with_all_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    created_at = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    updated_at = datetime(2025, 1, 2, 12, 0, tzinfo=UTC)

    inbound_number = InboundNumber(
        id=uuid.uuid4(),
        number="07700900123",
        provider="mmg",
        service=service,
        active=True,
        created_at=created_at,
        updated_at=updated_at,
    )

    serialized = inbound_number.serialize()

    assert isinstance(serialized, SerializedInboundNumber)
    assert serialized.id == str(inbound_number.id)
    assert serialized.number == "07700900123"
    assert serialized.provider == "mmg"
    assert serialized.service == {"id": str(service.id), "name": "Test Service"}
    assert serialized.active is True
    assert serialized.created_at == created_at.strftime(DATETIME_FORMAT)
    assert serialized.updated_at == updated_at.strftime(DATETIME_FORMAT)


def test_inbound_number_serializes_with_minimal_fields(notify_db_session):
    inbound_number = InboundNumber(
        id=uuid.uuid4(), number="07700900123", provider="mmg", active=True, created_at=datetime.utcnow()
    )

    serialized = inbound_number.serialize()

    assert serialized.id == str(inbound_number.id)
    assert serialized.number == "07700900123"
    assert serialized.provider == "mmg"
    assert serialized.service is None
    assert serialized.active is True
    assert serialized.created_at
    assert serialized.updated_at is None


def test_inbound_number_serialization_only_returns_defined_fields(notify_db_session):
    inbound_number = InboundNumber(
        id=uuid.uuid4(),
        number="07700900123",
        provider="mmg",
        active=True,
        created_at=datetime.utcnow(),
        fake_field="Should not be serialized",
    )

    serialized = inbound_number.serialize()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__dataclass_fields__.keys()) == {
        "id",
        "number",
        "provider",
        "service",
        "active",
        "created_at",
        "updated_at",
    }

    assert not hasattr(serialized, "fake_field")


def test_service_sms_sender_serializes_with_all_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    sms_sender = ServiceSmsSender(
        id=uuid.uuid4(),
        service=service,
        sms_sender="Notify",
        is_default=True,
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
    )

    serialized = sms_sender.serialize()

    assert isinstance(serialized, SerializedServiceSmsSender)
    assert serialized.id == str(sms_sender.id)
    assert serialized.service_id == str(service.id)
    assert serialized.sms_sender == "Notify"
    assert serialized.is_default is True
    assert serialized.created_at == "2025-01-01 12:00:00.000000"
    assert serialized.updated_at == "2025-01-02 12:00:00.000000"


def test_service_sms_sender_serializes_with_minimal_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    sms_sender = ServiceSmsSender(
        id=uuid.uuid4(),
        service=service,
        sms_sender="Notify",
        is_default=False,
    )

    serialized = sms_sender.serialize()

    assert serialized.id == str(sms_sender.id)
    assert serialized.service_id == str(service.id)
    assert serialized.sms_sender == "Notify"
    assert serialized.is_default is False
    assert serialized.created_at is None
    assert serialized.updated_at is None


def test_service_sms_sender_serialization_only_returns_defined_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    sms_sender = ServiceSmsSender(
        id=uuid.uuid4(),
        service=service,
        sms_sender="Notify",
        is_default=True,
        created_at=datetime.utcnow(),
        fake_field="Should not be serialized",
    )

    serialized = sms_sender.serialize()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__dataclass_fields__.keys()) == {
        "id",
        "service_id",
        "sms_sender",
        "is_default",
        "created_at",
        "updated_at",
    }

    assert not hasattr(serialized, "fake_field")


def test_service_serialization_for_dashboard_with_all_fields(notify_db_session):
    service = create_service(
        service_name="Test Service",
        active=True,
        restricted=True,
        message_limit=1000,
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
    )

    serialized = service.serialize_for_org_dashboard()

    assert isinstance(serialized, SerializedServiceOrgDashboard)
    assert serialized.id == str(service.id)
    assert serialized.name == "Test Service"
    assert serialized.active is True
    assert serialized.restricted is True


def test_service_serialization_for_dashboard_with_minimal_fields(notify_db_session):
    service = create_service(service_name="Test Service")

    serialized = service.serialize_for_org_dashboard()

    assert serialized.id == str(service.id)
    assert serialized.name == "Test Service"
    assert serialized.active is True
    assert serialized.restricted is False


def test_service_serialization_for_dashboard_only_returns_defined_fields(notify_db_session):
    service = create_service(
        service_name="Test Service",
        fake_field="Should not be serialized",
    )

    serialized = service.serialize_for_org_dashboard()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__dataclass_fields__.keys()) == {
        "id",
        "name",
        "active",
        "restricted",
    }

    assert not hasattr(serialized, "fake_field")
