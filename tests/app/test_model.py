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
    Complaint,
    EmailBranding,
    FactBilling,
    FactNotificationStatus,
    InboundNumber,
    InboundSms,
    InboundSmsHistory,
    InvitedOrganisationUser,
    InvitedUser,
    Job,
    LetterAttachment,
    LetterBranding,
    LetterCostThreshold,
    LetterRate,
    Notification,
    NotificationHistory,
    Organisation,
    Permission,
    Rate,
    ReportRequest,
    SerializedAnnualBilling,
    SerializedComplaint,
    SerializedEmailBranding,
    SerializedFreeSmsItems,
    SerializedInboundNumber,
    SerializedInboundSms,
    SerializedInvitedOrganisationUser,
    SerializedLetterAttachment,
    SerializedLetterRate,
    SerializedNotification,
    SerializedNotificationForCSV,
    SerializedOrganisation,
    SerializedOrganisationForList,
    SerializedRate,
    SerializedServiceCallbackApi,
    SerializedServiceContactList,
    SerializedServiceDataRetention,
    SerializedServiceEmailReplyTo,
    SerializedServiceLetterContact,
    SerializedServiceOrgDashboard,
    SerializedServiceSmsSender,
    SerializedTemplateFolder,
    SerializedUnsubscribeRequestReport,
    SerializedUser,
    SerializedUserForList,
    SerializedWebauthnCredential,
    ServiceCallbackApi,
    ServiceContactList,
    ServiceDataRetention,
    ServiceEmailReplyTo,
    ServiceGuestList,
    ServiceLetterContact,
    ServiceSmsSender,
    Template,
    TemplateFolder,
    TemplateHistory,
    UnsubscribeRequest,
    UnsubscribeRequestHistory,
    UnsubscribeRequestReport,
    User,
    WebauthnCredential,
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
    assert response["cost_details"].billable_sms_fragments == 2
    assert response["cost_details"].international_rate_multiplier == 1.0
    assert response["cost_details"].sms_rate == 0.0227
    assert response["cost_in_pounds"] == 0.0454


@pytest.mark.parametrize("status", ["created", "sending", "delivered", "returned-letter"])
def test_notification_serialize_with_cost_data_for_letter(client, sample_letter_template, letter_rate, status):
    notification = create_notification(sample_letter_template, billable_units=1, postage="second", status=status)

    response = notification.serialize_with_cost_data()

    assert response["is_cost_data_ready"] is True
    assert response["cost_details"].billable_sheets_of_paper == 1
    assert response["cost_details"].postage == "second"
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
    assert response["cost_details"].billable_sms_fragments == 2
    assert response["cost_details"].international_rate_multiplier == 1.0
    assert response["cost_details"].sms_rate == 0.0227
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
    assert response["cost_details"].billable_sheets_of_paper == 0
    assert response["cost_details"].postage == "first"
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

    assert serialized_data.services is not None
    assert len(serialized_data.services) == 1

    if service_filter_keys is None:
        # If None is passed, expect a flat list of IDs
        assert isinstance(serialized_data.services, list)
        assert all(isinstance(service_id, UUID) for service_id in serialized_data.services)
    else:
        # Otherwise, expect a list of dictionaries
        for service in serialized_data.services:
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

    assert isinstance(serialized, SerializedEmailBranding)
    assert serialized.id == str(email_branding.id)
    assert serialized.colour == "#000000"
    assert serialized.logo == "logo.png"
    assert serialized.name == "Test Brand"
    assert serialized.text == "Test Text"
    assert serialized.brand_type == "org"
    assert serialized.alt_text is None
    assert serialized.created_by == user_id
    assert serialized.created_at == created_at.strftime(DATETIME_FORMAT)
    assert serialized.updated_at == updated_at.strftime(DATETIME_FORMAT)


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
    assert serialized.created_at == created_at.strftime(DATETIME_FORMAT)
    assert serialized.updated_at == updated_at.strftime(DATETIME_FORMAT)


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
        id=uuid.uuid4(),
        name="Test Brand",
        filename="test-brand.svg",
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


def test_organisation_serializes_with_all_fields(notify_db_session):
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email_address="test@example.com",
        _password="password",
        auth_type="email_auth",
    )
    notify_db_session.add(user)

    email_branding = EmailBranding(
        id=uuid.uuid4(),
        name="Test Email Branding",
        brand_type="org",
        alt_text="Alt Text",
    )
    notify_db_session.add(email_branding)

    letter_branding = LetterBranding(
        id=uuid.uuid4(),
        name="Test Letter Branding",
        filename="test-letter-branding.svg",
    )
    notify_db_session.add(letter_branding)

    org = Organisation(
        id=uuid.uuid4(),
        name="Test Organisation",
        active=True,
        crown=True,
        organisation_type="central",
        letter_branding_id=letter_branding.id,
        email_branding_id=email_branding.id,
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
    assert result.agreement_signed_at == datetime(2023, 1, 1)
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
    org = Organisation(
        id=uuid.uuid4(),
        name="Test Organisation",
        active=True,
    )
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


def test_annual_billing_serialize_free_sms_items(notify_db_session):
    """Test the free SMS items serialization of annual billing"""
    service = create_service(service_name="Test Service")
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
    service = create_service(service_name="Test Service", restricted=False)
    notify_db_session.add(service)

    annual_billing = AnnualBilling(
        service=service,
        free_sms_fragment_limit=250000,
        financial_year_start=2022,
    )
    notify_db_session.add(annual_billing)
    notify_db_session.commit()

    result = annual_billing.serialize_free_sms_items()

    # Should only contain fields defined in SerializedFreeSmsItems dataclass
    assert set(result.__annotations__.keys()) == {"free_sms_fragment_limit", "financial_year_start"}


def test_annual_billing_serialize(notify_db_session):
    """Test the full serialization of annual billing"""
    service = create_service(service_name="Test Service")
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


def test_annual_billing_serialization_only_returns_defined_fields(notify_db_session):
    """Test to ensure we only get fields that are defined in the serialization dataclass"""
    service = create_service(service_name="Test Service")
    notify_db_session.add(service)
    annual_billing = AnnualBilling(
        service=service,
        free_sms_fragment_limit=250000,
        financial_year_start=2022,
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
    assert serialized.service.get("name") == "Test Service"
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


def test_service_sms_sender_serializes_with_all_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    sms_sender = ServiceSmsSender(
        id=uuid.uuid4(),
        service_id=service.id,
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
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.updated_at == datetime(2025, 1, 2, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)


def test_service_sms_sender_serializes_with_minimal_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    sms_sender = ServiceSmsSender(
        id=uuid.uuid4(),
        service_id=service.id,
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
        is_default=False,
    )

    serialized = sms_sender.serialize()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__annotations__.keys()) == {
        "id",
        "service_id",
        "sms_sender",
        "is_default",
        "archived",
        "inbound_number_id",
        "created_at",
        "updated_at",
    }


def test_service_serialization_for_dashboard_with_all_fields(notify_db_session):
    service = create_service(
        service_name="Test Service",
        active=True,
        restricted=True,
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
    )

    serialized = service.serialize_for_org_dashboard()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__annotations__.keys()) == {
        "id",
        "name",
        "active",
        "restricted",
    }


def test_user_serialization_return_all_fields(notify_db_session):
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email_address="test@example.com",
        created_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        auth_type="email_auth",
        current_session_id=uuid.uuid4(),
        failed_login_count=0,
        email_access_validated_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        logged_in_at=datetime(2020, 1, 2, 12, 0, tzinfo=UTC),
        mobile_number="07700900000",
        password_changed_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        platform_admin=False,
        state="active",
        take_part_in_research=True,
        receives_new_features_email=True,
        _password="password",
    )
    notify_db_session.add(user)
    notify_db_session.commit()

    serialized = user.serialize()

    assert isinstance(serialized, SerializedUser)
    assert serialized.id == user.id
    assert serialized.name == "Test User"
    assert serialized.email_address == "test@example.com"
    assert serialized.created_at == "2020-01-01T12:00:00.000000Z"
    assert serialized.auth_type == "email_auth"
    assert serialized.current_session_id == user.current_session_id
    assert serialized.failed_login_count == 0
    assert serialized.email_access_validated_at == "2020-01-01T12:00:00.000000Z"
    assert serialized.logged_in_at == "2020-01-02T12:00:00.000000Z"
    assert serialized.mobile_number == "07700900000"
    assert serialized.organisations == []
    assert serialized.password_changed_at == "2020-01-01 12:00:00.000000"
    assert serialized.permissions == {}
    assert serialized.organisation_permissions == {}
    assert serialized.platform_admin is False
    assert serialized.services == []
    assert serialized.can_use_webauthn is False
    assert serialized.state == "active"
    assert serialized.take_part_in_research is True
    assert serialized.receives_new_features_email is True


def test_user_serialization_only_returns_defined_fields(notify_db_session):
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email_address="test@example.com",
        created_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        auth_type="email_auth",
        current_session_id=uuid.uuid4(),
        failed_login_count=0,
        email_access_validated_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        logged_in_at=datetime(2020, 1, 2, 12, 0, tzinfo=UTC),
        mobile_number="07700900000",
        password_changed_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        platform_admin=False,
        state="active",
        take_part_in_research=True,
        receives_new_features_email=True,
        _password="password",
    )
    notify_db_session.add(user)
    notify_db_session.commit()

    serialized = user.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "name",
        "email_address",
        "created_at",
        "auth_type",
        "current_session_id",
        "failed_login_count",
        "email_access_validated_at",
        "logged_in_at",
        "mobile_number",
        "organisations",
        "password_changed_at",
        "permissions",
        "organisation_permissions",
        "platform_admin",
        "services",
        "can_use_webauthn",
        "state",
        "take_part_in_research",
        "receives_new_features_email",
    }


def test_user_serialization_with_list(notify_db_session):
    service = create_service(service_name="Test Service")
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email_address="test@example.com",
        created_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        auth_type="email_auth",
        current_session_id=uuid.uuid4(),
        failed_login_count=0,
        email_access_validated_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        logged_in_at=datetime(2020, 1, 2, 12, 0, tzinfo=UTC),
        mobile_number="07700900000",
        password_changed_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        platform_admin=False,
        state="active",
        take_part_in_research=True,
        receives_new_features_email=True,
        _password="password",
    )
    user.services.append(service)
    notify_db_session.add(user)
    notify_db_session.commit()

    serialized = user.serialize_for_users_list()

    assert isinstance(serialized, SerializedUserForList)
    assert serialized.id == user.id
    assert serialized.name == "Test User"
    assert serialized.email_address == "test@example.com"
    assert serialized.mobile_number == "07700900000"


def test_user_serialization_for_list_only_returns_defined_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email_address="test@example.com",
        created_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        auth_type="email_auth",
        current_session_id=uuid.uuid4(),
        failed_login_count=0,
        email_access_validated_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        logged_in_at=datetime(2020, 1, 2, 12, 0, tzinfo=UTC),
        mobile_number="07700900000",
        password_changed_at=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        platform_admin=False,
        state="active",
        take_part_in_research=True,
        receives_new_features_email=True,
        _password="password",
    )
    user.services.append(service)
    notify_db_session.add(user)
    notify_db_session.commit()

    serialized = user.serialize_for_users_list()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "name",
        "email_address",
        "mobile_number",
    }


def test_service_callback_api_serialization_returns_all_fields(notify_db_session, sample_user):
    service = create_service(service_name="Test Service")
    callback_api = ServiceCallbackApi(
        id=uuid.uuid4(),
        service_id=service.id,
        url="https://example.com/callback",
        _bearer_token="secret-token",
        updated_by_id=sample_user.id,
        updated_at=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(callback_api)
    notify_db_session.commit()

    serialized = callback_api.serialize()
    assert isinstance(serialized, SerializedServiceCallbackApi)
    assert serialized.id == str(callback_api.id)
    assert serialized.service_id == str(service.id)
    assert serialized.url == "https://example.com/callback"
    assert serialized.updated_at == datetime(2025, 1, 2, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)


def test_service_callback_api_serialization_only_returns_defined_fields(notify_db_session, sample_user):
    service = create_service(service_name="Test Service")
    callback_api = ServiceCallbackApi(
        id=uuid.uuid4(),
        service_id=service.id,
        url="https://example.com/callback",
        _bearer_token="secret-token",
        updated_by_id=sample_user.id,
        updated_at=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(callback_api)
    notify_db_session.commit()

    serialized = callback_api.serialize()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__annotations__.keys()) == {
        "id",
        "service_id",
        "url",
        "updated_by_id",
        "created_at",
        "updated_at",
    }


def test_template_folder_serialization_returns_all_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    parent_folder = create_template_folder(service, name="Parent Folder")
    folder = create_template_folder(service, name="Child Folder", parent=parent_folder)

    serialized = folder.serialize()
    assert isinstance(serialized, SerializedTemplateFolder)
    assert serialized.id == str(folder.id)
    assert serialized.name == "Child Folder"
    assert serialized.parent_id == str(parent_folder.id)
    assert serialized.service_id == str(service.id)
    assert serialized.users_with_permission == []


def test_template_folder_serialization_only_returns_defined_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    folder = create_template_folder(service, name="Child Folder")

    serialized = folder.serialize()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__annotations__.keys()) == {
        "id",
        "name",
        "parent_id",
        "service_id",
        "users_with_permission",
    }


def test_notification_serialization_for_csv_returns_all_fields(notify_db_session, sample_user, sample_job):
    # Create notification with a job and all fields populated
    with freeze_time("2025-01-15 12:00:00"):
        api_key = ApiKey(
            id=uuid.uuid4(),
            name="Test API Key",
            key_type="normal",
            service=sample_job.service,
            secret=uuid.uuid4(),
            created_by=sample_user,
        )
        notify_db_session.add(api_key)
        notify_db_session.commit()

        notification = create_notification(
            template=sample_job.template,
            job=sample_job,
            job_row_number=5,
            to_field="test@example.com",
            status="delivered",
            client_reference="test-ref-123",
            created_by_id=sample_user.id,
            api_key=api_key,
        )
        notify_db_session.commit()

        serialized = notification.serialize_for_csv()

        assert isinstance(serialized, SerializedNotificationForCSV)
        assert serialized.id == notification.id
        assert serialized.row_number == 6  # job_row_number is 0-indexed, displayed as 1-indexed
        assert serialized.recipient == "test@example.com"
        assert serialized.client_reference == "test-ref-123"
        assert serialized.template_name == sample_job.template.name
        assert serialized.template_type == sample_job.template.template_type
        assert serialized.job_name == sample_job.original_file_name
        assert serialized.status == notification.formatted_status
        assert serialized.created_at  # BST string representation
        assert serialized.created_by_name == sample_user.name
        assert serialized.created_by_email_address == sample_user.email_address
        assert serialized.api_key_name is not None


def test_notification_serialization_for_csv_with_minimal_fields(notify_db_session, sample_template):
    # Create notification without job and without created_by
    notification = create_notification(
        template=sample_template,
        job=None,
        to_field="minimal@example.com",
        status="created",
        client_reference=None,
        created_by_id=None,
    )
    notify_db_session.commit()

    serialized = notification.serialize_for_csv()

    assert isinstance(serialized, SerializedNotificationForCSV)
    assert serialized.id == notification.id
    assert serialized.row_number == ""  # No job_row_number
    assert serialized.recipient == "minimal@example.com"
    assert serialized.client_reference == ""  # None becomes empty string
    assert serialized.template_name == sample_template.name
    assert serialized.template_type == sample_template.template_type
    assert serialized.job_name == ""  # No job
    assert serialized.status == notification.formatted_status
    assert serialized.created_at  # BST string representation
    assert serialized.created_by_name is None
    assert serialized.created_by_email_address is None
    assert serialized.api_key_name is not None  # Created by create_notification


def test_notification_serialization_for_csv_only_returns_defined_fields(notify_db_session, sample_template):
    notification = create_notification(template=sample_template)
    notify_db_session.commit()

    serialized = notification.serialize_for_csv()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__annotations__.keys()) == {
        "id",
        "row_number",
        "recipient",
        "client_reference",
        "template_name",
        "template_type",
        "job_name",
        "status",
        "created_at",
        "created_by_name",
        "created_by_email_address",
        "api_key_name",
    }


def test_notification_serialization_returns_all_fields(notify_db_session, sample_template):
    notification = create_notification(template=sample_template)
    notify_db_session.commit()

    serialized = notification.serialize()

    assert isinstance(serialized, SerializedNotification)
    assert serialized.id == notification.id
    assert serialized.reference == notification.client_reference
    if notification.notification_type == EMAIL_TYPE:
        assert serialized.email_address == notification.to
    else:
        assert serialized.email_address is None
    assert serialized.phone_number == notification.to if notification.notification_type == SMS_TYPE else None
    assert serialized.type == notification.notification_type
    assert serialized.status == notification.status
    assert serialized.template.get("id") == notification.template.id
    assert serialized.body == notification.template.content
    assert serialized.subject == notification.subject
    assert serialized.created_at  # UTC string representation
    assert serialized.created_by_name is None
    assert serialized.sent_at is None
    assert serialized.completed_at is None
    assert serialized.scheduled_for is None
    assert serialized.postage is None
    assert serialized.one_click_unsubscribe_url is None
    assert serialized.estimated_delivery is None


def test_notification_serialization_only_returns_defined_fields(notify_db_session, sample_template):
    notification = create_notification(template=sample_template)
    notify_db_session.commit()

    serialized = notification.serialize()

    # Ensure only the defined fields are present in the serialized output
    assert set(serialized.__annotations__.keys()) == {
        "id",
        "reference",
        "email_address",
        "phone_number",
        "line_1",
        "line_2",
        "line_3",
        "line_4",
        "line_5",
        "line_6",
        "postcode",
        "type",
        "status",
        "template",
        "body",
        "subject",
        "created_at",
        "created_by_name",
        "sent_at",
        "completed_at",
        "scheduled_for",
        "postage",
        "one_click_unsubscribe_url",
        "estimated_delivery",
        "is_cost_data_ready",
        "cost_in_pounds",
        "cost_details",
    }


def test_notification_serialization_with_cost_data_returns_all_fields(notify_db_session, sample_template):
    rate = Rate(
        notification_type=SMS_TYPE,
        rate=0.05,
        valid_from=datetime(2024, 1, 1, tzinfo=UTC),
    )
    notify_db_session.add(rate)
    notification = create_notification(template=sample_template)
    notify_db_session.commit()

    serialized = notification.serialize_with_cost_data()

    assert isinstance(serialized, SerializedNotification)
    assert serialized.id == notification.id
    assert serialized.cost_details is not None
    assert serialized.cost_in_pounds == 0.05
    assert serialized.is_cost_data_ready is True


def test_invited_organisation_user_serialization_returns_all_fields(
    notify_db_session, sample_organisation, sample_user
):
    invite = InvitedOrganisationUser(
        id=uuid.uuid4(),
        email_address="test@example.com",
        invited_by_id=sample_user.id,
        organisation_id=sample_organisation.id,
        permissions="manage_service,manage_api_keys",
    )
    notify_db_session.add(invite)
    notify_db_session.commit()

    serialized = invite.serialize()

    assert isinstance(serialized, SerializedInvitedOrganisationUser)
    assert serialized.id == str(invite.id)
    assert serialized.email_address == "test@example.com"
    assert serialized.invited_by == str(invite.invited_by_id)
    assert serialized.organisation == str(invite.organisation_id)
    assert serialized.created_at is not None


def test_invited_organisation_user_serialization_only_returns_defined_fields(
    notify_db_session, sample_organisation, sample_user
):
    invite = InvitedOrganisationUser(
        id=uuid.uuid4(),
        email_address="test@example.com",
        invited_by_id=sample_user.id,
        organisation_id=sample_organisation.id,
        permissions="manage_service,manage_api_keys",
    )
    notify_db_session.add(invite)
    notify_db_session.commit()

    serialized = invite.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "email_address",
        "invited_by",
        "organisation",
        "created_at",
        "permissions",
        "status",
    }


def test_rate_serialization_returns_all_fields(notify_db_session):
    rate = Rate(
        id=uuid.uuid4(),
        notification_type=SMS_TYPE,
        rate=0.05,
        valid_from=datetime(2024, 1, 1, tzinfo=UTC),
    )
    notify_db_session.add(rate)
    notify_db_session.commit()

    serialized = rate.serialize()

    assert isinstance(serialized, SerializedRate)
    assert serialized.rate == 0.05
    assert serialized.valid_from == "2024-01-01T00:00:00"


def test_rate_serialization_only_returns_defined_fields(notify_db_session):
    rate = Rate(
        id=uuid.uuid4(),
        notification_type=SMS_TYPE,
        rate=0.05,
        valid_from=datetime(2024, 1, 1, tzinfo=UTC),
    )
    notify_db_session.add(rate)
    notify_db_session.commit()

    serialized = rate.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "rate",
        "valid_from",
    }


def test_imbound_sms_serialization_returns_all_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    inbound_sms = InboundSms(
        id=uuid.uuid4(),
        service_id=service.id,
        user_number="07700900123",
        notify_number="07700900456",
        provider="mmg",
        provider_reference="provider-ref-123",
        content="Test inbound SMS",
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(inbound_sms)
    notify_db_session.commit()

    serialized = inbound_sms.serialize()

    assert isinstance(serialized, SerializedInboundSms)
    assert serialized.id == str(inbound_sms.id)
    assert serialized.service_id == str(inbound_sms.service_id)
    assert serialized.user_number == "07700900123"
    assert serialized.notify_number == "07700900456"
    assert serialized.content == "Test inbound SMS"
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)


def test_inbound_sms_serialization_only_returns_defined_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    inbound_sms = InboundSms(
        id=uuid.uuid4(),
        service_id=service.id,
        user_number="07700900123",
        notify_number="07700900456",
        provider="mmg",
        provider_reference="provider-ref-123",
        content="Test inbound SMS",
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(inbound_sms)
    notify_db_session.commit()

    serialized = inbound_sms.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "created_at",
        "service_id",
        "notify_number",
        "user_number",
        "content",
    }


def test_letter_rate_serialization_returns_all_fields(notify_db_session):
    letter_rate = LetterRate(
        id=uuid.uuid4(),
        rate=0.75,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        post_class="first",
        crown=False,
        sheet_count=2,
    )
    notify_db_session.add(letter_rate)
    notify_db_session.commit()

    serialized = letter_rate.serialize()

    assert isinstance(serialized, SerializedLetterRate)
    assert serialized.sheet_count == 2
    assert serialized.start_date == letter_rate.start_date.strftime("%Y-%m-%dT%H:%M:%S")
    assert serialized.rate == "0.75"
    assert serialized.post_class == "first"


def test_letter_rate_serialization_only_returns_defined_fields(notify_db_session):
    letter_rate = LetterRate(
        id=uuid.uuid4(),
        rate=0.75,
        sheet_count=2,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        post_class="first",
        crown=False,
    )
    notify_db_session.add(letter_rate)
    notify_db_session.commit()

    serialized = letter_rate.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "sheet_count",
        "start_date",
        "rate",
        "post_class",
    }


def test_service_email_reply_to_serialization_returns_all_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    email_reply_to = ServiceEmailReplyTo(
        id=uuid.uuid4(),
        service_id=service.id,
        email_address="test@example.com",
        is_default=True,
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(email_reply_to)
    notify_db_session.commit()

    serialized = email_reply_to.serialize()

    assert isinstance(serialized, SerializedServiceEmailReplyTo)
    assert serialized.id == str(email_reply_to.id)
    assert serialized.service_id == str(service.id)
    assert serialized.email_address == "test@example.com"
    assert serialized.is_default is True
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.updated_at == datetime(2025, 1, 2, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)


def test_service_email_reply_to_serialization_only_returns_defined_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    email_reply_to = ServiceEmailReplyTo(
        id=uuid.uuid4(),
        service_id=service.id,
        email_address="test@example.com",
        is_default=True,
    )
    notify_db_session.add(email_reply_to)
    notify_db_session.commit()

    serialized = email_reply_to.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "service_id",
        "email_address",
        "is_default",
        "created_at",
        "updated_at",
        "archived",
    }


def test_service_letter_contact_serialization_returns_all_fields(notify_db_session):
    service = create_service(service_name="Test Service")

    service_letter = ServiceLetterContact(
        id=uuid.uuid4(),
        service_id=service.id,
        is_default=True,
        contact_block="some content block",
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(service_letter)
    notify_db_session.commit()

    serialized = service_letter.serialize()

    assert isinstance(serialized, SerializedServiceLetterContact)
    assert serialized.id == str(service_letter.id)
    assert serialized.service_id == str(service.id)
    assert serialized.is_default is True
    assert serialized.contact_block == "some content block"
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.updated_at is None
    assert serialized.archived is False


def test_service_letter_contact_serialization_only_returns_defined_fields(notify_db_session):
    service = create_service(service_name="Test Service")

    service_letter = ServiceLetterContact(
        id=uuid.uuid4(),
        service_id=service.id,
        is_default=True,
        contact_block="some content block",
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(service_letter)
    notify_db_session.commit()

    serialized = service_letter.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "service_id",
        "is_default",
        "contact_block",
        "created_at",
        "updated_at",
        "archived",
    }


def test_complaint_serialization_returns_all_fields(notify_db_session, sample_notification):
    complaint = Complaint(
        id=uuid.uuid4(),
        service_id=sample_notification.service_id,
        notification_id=sample_notification.id,
        ses_feedback_id="ses-feedback-123",
        complaint_type="bounce",
        complaint_date=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(complaint)
    notify_db_session.commit()

    serialized = complaint.serialize()

    assert isinstance(serialized, SerializedComplaint)
    assert serialized.id == str(complaint.id)
    assert serialized.notification_id == str(sample_notification.id)
    assert serialized.service_id == str(sample_notification.service_id)
    assert serialized.service_name == sample_notification.service.name
    assert serialized.ses_feedback_id == "ses-feedback-123"
    assert serialized.complaint_type == "bounce"
    assert serialized.complaint_date == datetime(2025, 1, 1, 10, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)


def test_complaint_serialization_only_returns_defined_fields(notify_db_session, sample_notification):
    complaint = Complaint(
        id=uuid.uuid4(),
        service_id=sample_notification.service_id,
        notification_id=sample_notification.id,
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(complaint)
    notify_db_session.commit()

    serialized = complaint.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "notification_id",
        "service_id",
        "service_name",
        "ses_feedback_id",
        "complaint_type",
        "complaint_date",
        "created_at",
    }


def test_service_data_retention_serialization_returns_all_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    data_retention = ServiceDataRetention(
        id=uuid.uuid4(),
        service_id=service.id,
        notification_type=SMS_TYPE,
        days_of_retention=30,
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(data_retention)
    notify_db_session.commit()

    serialized = data_retention.serialize()

    assert isinstance(serialized, SerializedServiceDataRetention)
    assert serialized.id == str(data_retention.id)
    assert serialized.service_id == str(service.id)
    assert serialized.service_name == service.name
    assert serialized.notification_type == SMS_TYPE
    assert serialized.days_of_retention == 30
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.updated_at == datetime(2025, 1, 2, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)


def test_service_data_retention_serialization_only_returns_defined_fields(notify_db_session):
    service = create_service(service_name="Test Service")
    data_retention = ServiceDataRetention(
        id=uuid.uuid4(),
        service_id=service.id,
        notification_type=SMS_TYPE,
        days_of_retention=30,
    )
    notify_db_session.add(data_retention)
    notify_db_session.commit()

    serialized = data_retention.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "service_id",
        "service_name",
        "notification_type",
        "days_of_retention",
        "created_at",
        "updated_at",
    }


def test_service_contact_list_serialization_returns_all_fields(notify_db_session, sample_user):
    service = create_service(service_name="Test Service")
    contact_list = ServiceContactList(
        id=uuid.uuid4(),
        service_id=service.id,
        original_file_name="test_contacts.csv",
        row_count=100,
        template_type=EMAIL_TYPE,
        created_by_id=sample_user.id,
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(contact_list)
    notify_db_session.commit()

    serialized = contact_list.serialize()

    assert isinstance(serialized, SerializedServiceContactList)
    assert serialized.id == str(contact_list.id)
    assert serialized.service_id == str(service.id)
    assert serialized.original_file_name == "test_contacts.csv"
    assert serialized.row_count == 100
    assert serialized.recent_job_count == 0
    assert serialized.has_jobs is False
    assert serialized.template_type == EMAIL_TYPE
    assert serialized.created_by == sample_user.name
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)


def test_service_contact_list_serialization_only_returns_defined_fields(notify_db_session, sample_user):
    service = create_service(service_name="Test Service")
    contact_list = ServiceContactList(
        id=uuid.uuid4(),
        service_id=service.id,
        original_file_name="test_contacts.csv",
        row_count=50,
        template_type=SMS_TYPE,
        created_by_id=sample_user.id,
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
    )
    notify_db_session.add(contact_list)
    notify_db_session.commit()

    serialized = contact_list.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "original_file_name",
        "row_count",
        "recent_job_count",
        "has_jobs",
        "template_type",
        "service_id",
        "created_by",
        "created_at",
    }


def test_webauthn_credential_serialization_returns_all_fields(notify_db_session, sample_user):
    webauthn_credential = WebauthnCredential(
        id=uuid.uuid4(),
        user_id=sample_user.id,
        name="Test Key",
        credential_data="credential-data-string",
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
        logged_in_at=datetime(2025, 1, 3, 12, 0, tzinfo=UTC),
        registration_response="some-registration-response",
    )
    notify_db_session.add(webauthn_credential)
    notify_db_session.commit()

    serialized = webauthn_credential.serialize()

    assert isinstance(serialized, SerializedWebauthnCredential)
    assert serialized.id == str(webauthn_credential.id)
    assert serialized.user_id == str(sample_user.id)
    assert serialized.name == "Test Key"
    assert serialized.credential_data == "credential-data-string"
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.updated_at == datetime(2025, 1, 2, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.logged_in_at == datetime(2025, 1, 3, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)


def test_webauthn_credential_serialization_only_returns_defined_fields(notify_db_session, sample_user):
    webauthn_credential = WebauthnCredential(
        id=uuid.uuid4(),
        user_id=sample_user.id,
        name="Test Key",
        credential_data="credential-data-string",
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        registration_response="some-registration-response",
    )
    notify_db_session.add(webauthn_credential)
    notify_db_session.commit()

    serialized = webauthn_credential.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "user_id",
        "name",
        "credential_data",
        "created_at",
        "updated_at",
        "logged_in_at",
    }


def test_letter_attachment_serialization_returns_all_fields(notify_db_session, sample_service, sample_user):
    letter_attachment = LetterAttachment(
        id=uuid.uuid4(),
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        created_by_id=sample_user.id,
        archived_at=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
        archived_by_id=sample_user.id,
        original_filename="attachment.pdf",
        page_count=5,
    )
    notify_db_session.add(letter_attachment)
    notify_db_session.commit()

    serialized = letter_attachment.serialize()

    assert isinstance(serialized, SerializedLetterAttachment)
    assert serialized.id == str(letter_attachment.id)
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.created_by_id == str(sample_user.id)
    assert serialized.archived_at == datetime(2025, 1, 2, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.archived_by_id == str(sample_user.id)
    assert serialized.original_filename == "attachment.pdf"
    assert serialized.page_count == 5


def test_letter_attachment_serialization_only_returns_defined_fields(notify_db_session, sample_service, sample_user):
    letter_attachment = LetterAttachment(
        id=uuid.uuid4(),
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        created_by_id=sample_user.id,
        original_filename="attachment.pdf",
        page_count=3,
    )
    notify_db_session.add(letter_attachment)
    notify_db_session.commit()

    serialized = letter_attachment.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "id",
        "created_at",
        "created_by_id",
        "archived_at",
        "archived_by_id",
        "original_filename",
        "page_count",
    }


def test_unsubscribe_request_report_serialization(notify_db_session, sample_service):
    unsubscribe_request = UnsubscribeRequestReport(
        id=uuid.uuid4(),
        count=5,
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        earliest_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        latest_timestamp=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
        processed_by_service_at=datetime(2025, 1, 1, 13, 0, tzinfo=UTC),
        service_id=sample_service.id,
    )
    notify_db_session.add(unsubscribe_request)
    notify_db_session.commit()

    serialized = unsubscribe_request.serialize()

    assert isinstance(serialized, SerializedUnsubscribeRequestReport)
    assert serialized.batch_id == str(unsubscribe_request.id)
    assert serialized.count == 5
    assert serialized.created_at == datetime(2025, 1, 1, 12, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.earliest_timestamp == datetime(2025, 1, 1, 10, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.latest_timestamp == datetime(2025, 1, 1, 11, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.processed_by_service_at == datetime(2025, 1, 1, 13, 0, tzinfo=UTC).strftime(DATETIME_FORMAT)
    assert serialized.is_a_batched_report is True
    assert serialized.service_id == str(sample_service.id)


def test_unsubscribe_request_report_unbatched_requests_serialization(
    notify_db_session, sample_notification, sample_service
):
    unsubscribe_request = UnsubscribeRequestReport(
        id=uuid.uuid4(),
        count=1,
        earliest_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        latest_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        service_id=sample_service.id,
    )
    notify_db_session.add(unsubscribe_request)
    notify_db_session.commit()

    unbatched_requests = [
        UnsubscribeRequest(
            id=uuid.uuid4(),
            template_id=sample_notification.template.id,
            template_version=sample_notification.template.version,
            service_id=sample_service.id,
            email_address="user@example.com",
            created_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            unsubscribe_request_report_id=unsubscribe_request.id,
            notification_id=sample_notification.id,
        )
    ]
    notify_db_session.add_all(unbatched_requests)
    notify_db_session.commit()

    serialized = unsubscribe_request.serialize_unbatched_requests(unbatched_requests)

    assert isinstance(serialized, SerializedUnsubscribeRequestReport)


def test_unsubscribe_request_report_serialization_only_returns_defined_fields(notify_db_session, sample_service):
    unsubscribe_request = UnsubscribeRequestReport(
        id=uuid.uuid4(),
        count=3,
        earliest_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        latest_timestamp=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
        service_id=sample_service.id,
    )
    notify_db_session.add(unsubscribe_request)
    notify_db_session.commit()

    serialized = unsubscribe_request.serialize()

    assert set(serialized.__annotations__.keys()) == {
        "batch_id",
        "count",
        "created_at",
        "earliest_timestamp",
        "latest_timestamp",
        "processed_by_service_at",
        "is_a_batched_report",
        "will_be_archived_at",
        "service_id",
    }
