from uuid import uuid4

import pytest
from flask import current_app
from freezegun import freeze_time
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.clients.redis import daily_limit_cache_key
from notifications_utils.recipient_validation.errors import InvalidPhoneError

import app
from app.constants import (
    EMAIL_TYPE,
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_SMS_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_TYPES,
    SMS_TO_UK_LANDLINES,
    SMS_TYPE,
)
from app.dao import templates_dao
from app.models import ServicePermission
from app.notifications.process_notifications import (
    create_content_for_notification,
)
from app.notifications.validators import (
    check_if_service_can_send_files_by_email,
    check_is_message_too_long,
    check_notification_content_is_not_empty,
    check_rate_limiting,
    check_service_email_reply_to_id,
    check_service_letter_contact_id,
    check_service_over_api_rate_limit,
    check_service_over_daily_message_limit,
    check_service_sms_sender_id,
    check_template_is_active,
    check_template_is_for_notification_type,
    service_can_send_to_recipient,
    validate_address,
    validate_and_format_recipient,
    validate_template,
)
from app.serialised_models import (
    SerialisedAPIKeyCollection,
    SerialisedService,
    SerialisedTemplate,
)
from app.utils import get_template_instance
from app.v2.errors import (
    BadRequestError,
    RateLimitError,
    TooManyRequestsError,
    ValidationError,
)
from tests.app.db import (
    create_api_key,
    create_letter_contact,
    create_reply_to_email,
    create_service,
    create_service_guest_list,
    create_service_sms_sender,
    create_template,
)
from tests.conftest import set_config


# all of these tests should have redis enabled (except where we specifically disable it)
@pytest.fixture(scope="module", autouse=True)
def enable_redis(notify_api):
    with set_config(notify_api, "REDIS_ENABLED", True):
        yield


class TestCheckServiceMessageLimit:
    @pytest.mark.parametrize("key_type", ["team", "normal"])
    @pytest.mark.parametrize("notification_type", NOTIFICATION_TYPES + [INTERNATIONAL_SMS_TYPE])
    def test_check_service_message_limit_in_cache_under_message_limit_passes(
        self, sample_service, mocker, notification_type, key_type
    ):
        serialised_service = SerialisedService.from_id(sample_service.id)
        mock_get = mocker.patch("app.notifications.validators.redis_store.get", return_value="1")
        mock_set = mocker.patch("app.notifications.validators.redis_store.set")
        check_service_over_daily_message_limit(serialised_service, key_type, notification_type=notification_type)
        assert mock_get.call_args_list == [
            mocker.call(daily_limit_cache_key(sample_service.id, notification_type=notification_type)),
        ]
        assert mock_set.call_args_list == []

    @pytest.mark.parametrize("notification_type", NOTIFICATION_TYPES + [INTERNATIONAL_SMS_TYPE])
    def test_check_service_over_daily_message_limit_should_not_interact_with_cache_for_test_key(
        self, sample_service, mocker, notification_type
    ):
        mocker.patch("app.notifications.validators.redis_store")
        mock_get = mocker.patch("app.notifications.validators.redis_store.get", side_effect=[None])
        serialised_service = SerialisedService.from_id(sample_service.id)
        check_service_over_daily_message_limit(serialised_service, "test", notification_type=notification_type)
        assert mock_get.call_args_list == []

    @pytest.mark.parametrize("key_type", ["team", "normal"])
    @pytest.mark.parametrize("notification_type", NOTIFICATION_TYPES + [INTERNATIONAL_SMS_TYPE])
    def test_check_service_over_daily_message_limit_should_set_cache_value_as_zero_if_cache_not_set(
        self, sample_service, mocker, notification_type, key_type
    ):
        serialised_service = SerialisedService.from_id(sample_service.id)
        with freeze_time("2016-01-01 12:00:00.000000"):
            mock_set = mocker.patch("app.notifications.validators.redis_store.set")
            check_service_over_daily_message_limit(serialised_service, key_type, notification_type=notification_type)

            assert mock_set.call_args_list == [
                mocker.call(daily_limit_cache_key(sample_service.id, notification_type=notification_type), 0, ex=86400),
            ]

    @pytest.mark.parametrize("notification_type", NOTIFICATION_TYPES + [INTERNATIONAL_SMS_TYPE])
    def test_check_service_over_daily_message_limit_does_nothing_if_redis_disabled(
        self, notify_api, sample_service, mocker, notification_type
    ):
        serialised_service = SerialisedService.from_id(sample_service.id)
        with set_config(notify_api, "REDIS_ENABLED", False):
            mock_cache_key = mocker.patch("notifications_utils.clients.redis.daily_limit_cache_key")
            check_service_over_daily_message_limit(serialised_service, "normal", notification_type=notification_type)
            assert mock_cache_key.method_calls == []

    @pytest.mark.parametrize("key_type", ["team", "normal"])
    @pytest.mark.parametrize("notification_type", NOTIFICATION_TYPES + [INTERNATIONAL_SMS_TYPE])
    def test_check_service_message_limit_over_message_limit_fails_with_cold_ie_missing_cache_value(
        self, mocker, notify_db_session, notification_type, key_type
    ):
        service = create_service(
            email_message_limit=4, letter_message_limit=4, sms_message_limit=4, international_sms_message_limit=4
        )
        mocker.patch("app.redis_store.get", return_value=None)

        with pytest.raises(TooManyRequestsError) as e:
            check_service_over_daily_message_limit(
                service, key_type, notification_type=notification_type, num_notifications=10
            )
        tmr_error: TooManyRequestsError = e.value
        assert tmr_error.status_code == 429
        assert tmr_error.limit_name == notification_type
        assert tmr_error.sending_limit == 4
        assert tmr_error.message == f"Exceeded send limits ({notification_type}: 4) for today"
        assert tmr_error.fields == []

    @pytest.mark.parametrize("key_type", ["team", "normal"])
    @pytest.mark.parametrize("notification_type", NOTIFICATION_TYPES + [INTERNATIONAL_SMS_TYPE])
    def test_check_service_message_limit_over_message_limit_fails(
        self, mocker, notify_db_session, notification_type, key_type
    ):
        service = create_service(
            email_message_limit=4,
            letter_message_limit=4,
            sms_message_limit=4,
            international_sms_message_limit=4,
        )
        mocker.patch("app.redis_store.get", return_value="5")

        with pytest.raises(TooManyRequestsError) as e:
            check_service_over_daily_message_limit(service, key_type, notification_type=notification_type)
        tmr_error: TooManyRequestsError = e.value
        assert tmr_error.status_code == 429
        assert tmr_error.limit_name == notification_type
        assert tmr_error.sending_limit == 4
        assert tmr_error.message == f"Exceeded send limits ({notification_type}: 4) for today"
        assert tmr_error.fields == []

    @pytest.mark.parametrize("key_type", ["team", "normal"])
    @pytest.mark.parametrize("notification_type", NOTIFICATION_TYPES + [INTERNATIONAL_SMS_TYPE])
    def test_check_service_message_limit_check_with_multiple_notifications_for_jobs(
        self, mocker, notify_db_session, notification_type, key_type
    ):
        service = create_service(
            email_message_limit=10,
            letter_message_limit=10,
            sms_message_limit=10,
            international_sms_message_limit=10,
        )
        mocker.patch("app.redis_store.get", return_value="9")

        with pytest.raises(TooManyRequestsError) as e:
            check_service_over_daily_message_limit(
                service, key_type, notification_type=notification_type, num_notifications=2
            )
        tmr_error: TooManyRequestsError = e.value
        assert tmr_error.status_code == 429
        assert tmr_error.limit_name == notification_type
        assert tmr_error.sending_limit == 10
        assert tmr_error.message == f"Exceeded send limits ({notification_type}: 10) for today"
        assert tmr_error.fields == []


@pytest.mark.parametrize("template_type, notification_type", [(EMAIL_TYPE, EMAIL_TYPE), (SMS_TYPE, SMS_TYPE)])
def test_check_template_is_for_notification_type_pass(template_type, notification_type):
    assert (
        check_template_is_for_notification_type(notification_type=notification_type, template_type=template_type)
        is None
    )


@pytest.mark.parametrize("template_type, notification_type", [(SMS_TYPE, EMAIL_TYPE), (EMAIL_TYPE, SMS_TYPE)])
def test_check_template_is_for_notification_type_fails_when_template_type_does_not_match_notification_type(
    template_type, notification_type
):
    with pytest.raises(BadRequestError) as e:
        check_template_is_for_notification_type(notification_type=notification_type, template_type=template_type)
    assert e.value.status_code == 400
    error_message = f"{template_type} template is not suitable for {notification_type} notification"
    assert e.value.message == error_message
    assert e.value.fields == [{"template": error_message}]


def test_check_template_is_active_passes(sample_template):
    assert check_template_is_active(sample_template) is None


def test_check_template_is_active_fails(sample_template):
    sample_template.archived = True
    from app.dao.templates_dao import dao_update_template

    dao_update_template(sample_template)
    with pytest.raises(BadRequestError) as e:
        check_template_is_active(sample_template)
    assert e.value.status_code == 400
    assert e.value.message == "Template has been deleted"
    assert e.value.fields == [{"template": "Template has been deleted"}]


@pytest.mark.parametrize("key_type", ["test", "normal"])
def test_service_can_send_to_recipient_passes(key_type, notify_db_session):
    trial_mode_service = create_service(service_name="trial mode", restricted=True)
    serialised_service = SerialisedService.from_id(trial_mode_service.id)
    assert (
        service_can_send_to_recipient(trial_mode_service.users[0].email_address, key_type, serialised_service) is None
    )
    assert (
        service_can_send_to_recipient(trial_mode_service.users[0].mobile_number, key_type, serialised_service) is None
    )


@pytest.mark.parametrize(
    "user_number, recipient_number",
    [
        ["0048601234567", "+486 012 34567"],
        ["07513332413", "(07513) 332413"],
    ],
)
def test_service_can_send_to_recipient_passes_with_non_normalised_number(sample_service, user_number, recipient_number):
    sample_service.users[0].mobile_number = user_number

    serialised_service = SerialisedService.from_id(sample_service.id)

    assert service_can_send_to_recipient(recipient_number, "team", serialised_service) is None


@pytest.mark.parametrize(
    "user_email, recipient_email",
    [
        ["test@example.com", "TeSt@EXAMPLE.com"],
    ],
)
def test_service_can_send_to_recipient_passes_with_non_normalised_email(sample_service, user_email, recipient_email):
    sample_service.users[0].email_address = user_email

    serialised_service = SerialisedService.from_id(sample_service.id)

    assert service_can_send_to_recipient(recipient_email, "team", serialised_service) is None


@pytest.mark.parametrize("key_type", ["test", "normal"])
def test_service_can_send_to_recipient_passes_for_live_service_non_team_member(key_type, sample_service):
    serialised_service = SerialisedService.from_id(sample_service.id)
    assert service_can_send_to_recipient("some_other_email@test.com", key_type, serialised_service) is None
    assert service_can_send_to_recipient("07513332413", key_type, serialised_service) is None


def test_service_can_send_to_recipient_passes_for_guest_list_recipient_passes(sample_service):
    create_service_guest_list(sample_service, email_address="some_other_email@test.com")
    assert service_can_send_to_recipient("some_other_email@test.com", "team", sample_service) is None
    create_service_guest_list(sample_service, mobile_number="07513332413")
    assert service_can_send_to_recipient("07513332413", "team", sample_service) is None


@pytest.mark.parametrize(
    "recipient",
    [
        {"email_address": "some_other_email@test.com"},
        {"mobile_number": "07513332413"},
    ],
)
def test_service_can_send_to_recipient_fails_when_ignoring_guest_list(
    notify_db_session,
    sample_service,
    recipient,
):
    create_service_guest_list(sample_service, **recipient)
    with pytest.raises(BadRequestError) as exec_info:
        service_can_send_to_recipient(
            next(iter(recipient.values())),
            "team",
            sample_service,
            allow_guest_list_recipients=False,
        )
    assert exec_info.value.status_code == 400
    assert exec_info.value.message == "Can’t send to this recipient using a team-only API key"
    assert exec_info.value.fields == []


@pytest.mark.parametrize("recipient", ["07513332413", "some_other_email@test.com"])
@pytest.mark.parametrize(
    "key_type, error_message",
    [
        ("team", "Can’t send to this recipient using a team-only API key"),
        (
            "normal",
            "Can’t send to this recipient when service is in trial mode – see https://www.notifications.service.gov.uk/trial-mode",
        ),
    ],
)
def test_service_can_send_to_recipient_fails_when_recipient_is_not_on_team(
    recipient,
    key_type,
    error_message,
    notify_db_session,
):
    trial_mode_service = create_service(service_name="trial mode", restricted=True)
    with pytest.raises(BadRequestError) as exec_info:
        service_can_send_to_recipient(recipient, key_type, trial_mode_service)
    assert exec_info.value.status_code == 400
    assert exec_info.value.message == error_message
    assert exec_info.value.fields == []


def test_service_can_send_to_recipient_fails_when_mobile_number_is_not_on_team(sample_service):
    with pytest.raises(BadRequestError) as e:
        service_can_send_to_recipient("0758964221", "team", sample_service)
    assert e.value.status_code == 400
    assert e.value.message == "Can’t send to this recipient using a team-only API key"
    assert e.value.fields == []


@pytest.mark.parametrize("char_count", [612, 0, 494, 200, 918])
@pytest.mark.parametrize("show_prefix", [True, False])
@pytest.mark.parametrize("template_type", ["sms", "email", "letter"])
def test_check_is_message_too_long_passes(notify_db_session, show_prefix, char_count, template_type):
    service = create_service(prefix_sms=show_prefix)
    t = create_template(service=service, content="a" * char_count, template_type=template_type)
    template = templates_dao.dao_get_template_by_id_and_service_id(template_id=t.id, service_id=service.id)
    template_with_content = get_template_instance(template=template.__dict__, values={})
    assert check_is_message_too_long(template_with_content) is None


@pytest.mark.parametrize("char_count", [919, 6000])
@pytest.mark.parametrize("show_prefix", [True, False])
def test_check_is_message_too_long_fails(notify_db_session, show_prefix, char_count):
    with pytest.raises(BadRequestError) as e:
        service = create_service(prefix_sms=show_prefix)
        t = create_template(service=service, content="a" * char_count, template_type="sms")
        template = templates_dao.dao_get_template_by_id_and_service_id(template_id=t.id, service_id=service.id)
        template_with_content = get_template_instance(template=template.__dict__, values={})
        check_is_message_too_long(template_with_content)
    assert e.value.status_code == 400
    expected_message = (
        f"Your message is too long. "
        f"Text messages cannot be longer than {SMS_CHAR_COUNT_LIMIT} characters. "
        f"Your message is {char_count} characters long."
    )
    assert e.value.message == expected_message
    assert e.value.fields == []


def test_check_is_message_too_long_passes_for_long_email(sample_service):
    email_character_count = 2_000_001
    t = create_template(service=sample_service, content="a" * email_character_count, template_type="email")
    template = templates_dao.dao_get_template_by_id_and_service_id(template_id=t.id, service_id=t.service_id)
    template_with_content = get_template_instance(template=template.__dict__, values={})
    with pytest.raises(BadRequestError) as e:
        check_is_message_too_long(template_with_content)
    assert e.value.status_code == 400
    expected_message = (
        "Your message is too long. " + "Emails cannot be longer than 2000000 bytes. " + "Your message is 2000001 bytes."
    )
    assert e.value.message == expected_message
    assert e.value.fields == []


def test_check_notification_content_is_not_empty_passes(notify_api, mocker, sample_service):
    template_id = create_template(sample_service, content="Content is not empty").id
    template = SerialisedTemplate.from_id_and_service_id(template_id=template_id, service_id=sample_service.id)
    template_with_content = create_content_for_notification(template, {})
    assert check_notification_content_is_not_empty(template_with_content) is None


@pytest.mark.parametrize("template_content,notification_values", [("", {}), ("((placeholder))", {"placeholder": ""})])
def test_check_notification_content_is_not_empty_fails(
    notify_api, mocker, sample_service, template_content, notification_values
):
    template_id = create_template(sample_service, content=template_content).id
    template = SerialisedTemplate.from_id_and_service_id(template_id=template_id, service_id=sample_service.id)
    template_with_content = create_content_for_notification(template, notification_values)
    with pytest.raises(BadRequestError) as e:
        check_notification_content_is_not_empty(template_with_content)
    assert e.value.status_code == 400
    assert e.value.message == "Your message is empty."
    assert e.value.fields == []


def test_validate_template(sample_service):
    template = create_template(sample_service, template_type="email")
    validate_template(template.id, {}, sample_service, "email")


@pytest.mark.parametrize("check_char_count", [True, False])
def test_validate_template_calls_all_validators(mocker, fake_uuid, sample_service, check_char_count):
    template = create_template(sample_service, template_type="email")
    mock_check_type = mocker.patch("app.notifications.validators.check_template_is_for_notification_type")
    mock_check_if_active = mocker.patch("app.notifications.validators.check_template_is_active")
    mock_create_conent = mocker.patch(
        "app.notifications.validators.create_content_for_notification", return_value="content"
    )
    mock_check_not_empty = mocker.patch("app.notifications.validators.check_notification_content_is_not_empty")
    mock_check_message_is_too_long = mocker.patch("app.notifications.validators.check_is_message_too_long")
    template, template_with_content = validate_template(
        template.id, {}, sample_service, "email", check_char_count=check_char_count
    )

    mock_check_type.assert_called_once_with("email", "email")
    mock_check_if_active.assert_called_once_with(template)
    mock_create_conent.assert_called_once_with(template, {})
    mock_check_not_empty.assert_called_once_with("content")
    if check_char_count:
        mock_check_message_is_too_long.assert_called_once_with("content")
    else:
        assert not mock_check_message_is_too_long.called


def test_validate_template_calls_all_validators_exception_message_too_long(mocker, sample_service):
    template = create_template(sample_service, template_type="email")
    mock_check_type = mocker.patch("app.notifications.validators.check_template_is_for_notification_type")
    mock_check_if_active = mocker.patch("app.notifications.validators.check_template_is_active")
    mock_create_conent = mocker.patch(
        "app.notifications.validators.create_content_for_notification", return_value="content"
    )
    mock_check_not_empty = mocker.patch("app.notifications.validators.check_notification_content_is_not_empty")
    mock_check_message_is_too_long = mocker.patch("app.notifications.validators.check_is_message_too_long")
    template, template_with_content = validate_template(
        template.id, {}, sample_service, "email", check_char_count=False
    )

    mock_check_type.assert_called_once_with("email", "email")
    mock_check_if_active.assert_called_once_with(template)
    mock_create_conent.assert_called_once_with(template, {})
    mock_check_not_empty.assert_called_once_with("content")
    assert not mock_check_message_is_too_long.called


@pytest.mark.parametrize("key_type", ["team", "live", "test"])
@pytest.mark.parametrize("remaining_tokens", (0, -1))
def test_check_token_bucket_service_over_api_rate_limit_when_exceed_rate_limit_request_fails_raises_error(
    key_type, mocker, remaining_tokens
):
    service = create_service(service_name=str(uuid4()), service_permissions=["token_bucket"], restricted=True)
    with freeze_time("2016-01-01 12:00:00.000000"):
        if key_type == "live":
            api_key_type = "normal"
        else:
            api_key_type = key_type

        mocker.patch("app.redis_store.get_remaining_bucket_tokens", return_value=remaining_tokens)
        api_key = create_api_key(service, key_type=api_key_type)
        serialised_service = SerialisedService.from_id(service.id)
        serialised_api_key = SerialisedAPIKeyCollection.from_service_id(serialised_service.id)[0]

        with pytest.raises(RateLimitError) as e:
            check_service_over_api_rate_limit(serialised_service, serialised_api_key.key_type)

        assert app.redis_store.get_remaining_bucket_tokens.call_args_list == [
            mocker.call(
                key=f"{str(service.id)}-tokens-{api_key.key_type}", replenish_per_sec=50, bucket_max=1_000, bucket_min=0
            )
        ]
        assert e.value.status_code == 429
        assert e.value.message == (
            f"Exceeded rate limit for key type {key_type.upper()} of 3000 requests per 60 seconds"
        )
        assert e.value.fields == []


@pytest.mark.parametrize(
    "extra_create_service_args, expected_replenish_per_sec, expected_bucket_max",
    (
        ({}, 50, 1_000),
        ({"rate_limit": 24_000}, 400, 1_000),
        ({"rate_limit": 10}, 0.16666666666666666, 4),
        ({"rate_limit": 1}, 0.016666666666666666, 1),
        ({"rate_limit": 0}, 0, 0),
    ),
)
@pytest.mark.parametrize("remaining_tokens", (1, 999, None))
def test_check_token_bucket_service_over_api_rate_limit_when_rate_limit_has_not_exceeded_limit_succeeds(
    mocker,
    remaining_tokens,
    extra_create_service_args,
    expected_replenish_per_sec,
    expected_bucket_max,
):
    service = create_service(
        service_name=str(uuid4()),
        service_permissions=["token_bucket"],
        restricted=True,
        **extra_create_service_args,
    )
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch("app.redis_store.get_remaining_bucket_tokens", return_value=remaining_tokens)

        api_key = create_api_key(service)
        serialised_service = SerialisedService.from_id(service.id)
        serialised_api_key = SerialisedAPIKeyCollection.from_service_id(service.id)[0]

        check_service_over_api_rate_limit(serialised_service, serialised_api_key.key_type)
        assert app.redis_store.get_remaining_bucket_tokens.call_args_list == [
            mocker.call(
                key=f"{str(service.id)}-tokens-{api_key.key_type}",
                replenish_per_sec=expected_replenish_per_sec,
                bucket_max=expected_bucket_max,
                bucket_min=0,
            )
        ]


@pytest.mark.parametrize("service_permissions", ([], ["token_bucket"]))
def test_check_service_over_api_rate_limit_should_do_nothing_if_limiting_is_disabled(mocker, service_permissions):
    service = create_service(service_name=str(uuid4()), service_permissions=service_permissions, restricted=True)
    with freeze_time("2016-01-01 12:00:00.000000"):
        current_app.config["API_RATE_LIMIT_ENABLED"] = False

        mocker.patch("app.redis_store.exceeded_rate_limit", return_value=False)

        create_api_key(service)
        serialised_service = SerialisedService.from_id(service.id)
        serialised_api_key = SerialisedAPIKeyCollection.from_service_id(serialised_service.id)[0]

        check_service_over_api_rate_limit(serialised_service, serialised_api_key.key_type)
        assert app.redis_store.exceeded_rate_limit.call_args_list == []


@pytest.mark.parametrize("notification_type", NOTIFICATION_TYPES)
def test_check_rate_limiting_validates_api_rate_limit_and_daily_limit(notify_db_session, mocker, notification_type):
    mock_rate_limit = mocker.patch("app.notifications.validators.check_service_over_api_rate_limit")
    mock_daily_limit = mocker.patch("app.notifications.validators.check_service_over_daily_message_limit")
    service = create_service()
    api_key = create_api_key(service=service)

    check_rate_limiting(service, api_key, notification_type=notification_type)

    mock_rate_limit.assert_called_once_with(service, api_key.key_type)
    assert mock_daily_limit.call_args_list == [
        mocker.call(service, api_key.key_type, notification_type=notification_type),
    ]


@pytest.mark.parametrize("key_type", ["test", "normal"])
def test_validate_and_format_recipient_fails_when_international_number_and_service_does_not_allow_int_sms(
    key_type,
    notify_db_session,
):
    service = create_service(service_permissions=[SMS_TYPE])
    service_model = SerialisedService.from_id(service.id)
    with pytest.raises(BadRequestError) as e:
        validate_and_format_recipient("20-12-1234-1234", key_type, service_model, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == "Cannot send to international mobile numbers"
    assert e.value.fields == []


@pytest.mark.parametrize("key_type", [KEY_TYPE_TEST, KEY_TYPE_NORMAL])
def test_validate_and_format_recipient_succeeds_with_international_numbers_if_service_does_allow_int_sms(
    key_type, sample_service_full_permissions
):
    service_model = SerialisedService.from_id(sample_service_full_permissions.id)
    result = validate_and_format_recipient("20-12-1234-1234", key_type, service_model, SMS_TYPE)
    assert result == {
        "international": True,
        "normalised_to": "201212341234",
        "unformatted_recipient": "20-12-1234-1234",
        "phone_prefix": "20",
        "rate_multiplier": 7,
    }


def test_validate_and_format_recipient_raises_when_service_over_daily_limit_for_international_sms(
    sample_service_full_permissions, mocker
):
    service = create_service(international_sms_message_limit=4, service_permissions=["sms", "international_sms"])
    mocker.patch("app.redis_store.get", return_value="5")

    with pytest.raises(TooManyRequestsError) as e:
        validate_and_format_recipient("20-12-1234-1234", KEY_TYPE_NORMAL, service, SMS_TYPE)
    expected_error: TooManyRequestsError = e.value
    assert expected_error.status_code == 429
    assert expected_error.limit_name == "international_sms"
    assert expected_error.sending_limit == 4
    assert expected_error.message == "Exceeded send limits (international_sms: 4) for today"
    assert expected_error.fields == []


def test_validate_and_format_recipient_doesnt_raise_for_crown_dependency_num_when_service_over_daily_intl_sms_limit(
    sample_service_full_permissions, mocker
):
    service = create_service(
        international_sms_message_limit=4,
        service_permissions=["sms", "international_sms"],
    )
    mocker.patch("app.redis_store.get", return_value="5")

    result = validate_and_format_recipient("+44 7797 100 100", KEY_TYPE_NORMAL, service, SMS_TYPE)

    assert result == {
        "international": True,
        "normalised_to": "447797100100",
        "unformatted_recipient": "+44 7797 100 100",
        "phone_prefix": "44",
        "rate_multiplier": 2,
    }


@pytest.mark.parametrize(
    "recipient, expected_normalised, expected_international, expected_prefix, expected_rate_multiplier",
    [
        ("7900900123", "447900900123", False, "44", 1),  # UK
        ("+447900900123", "447900900123", False, "44", 1),  # UK
        ("07797292290", "447797292290", True, "44", 2),  # UK (Jersey)
        ("74957108855", "74957108855", True, "7", 10),  # Russia
        ("360623400400", "3623400400", True, "36", 2),
    ],  # Hungary
)
def test_validate_and_format_recipient_gets_correct_info_for_international_numbers(
    sample_job,
    recipient,
    expected_normalised,
    expected_international,
    expected_prefix,
    expected_rate_multiplier,
):
    result = validate_and_format_recipient(recipient, KEY_TYPE_NORMAL, sample_job.service, SMS_TYPE)
    assert result == {
        "unformatted_recipient": recipient,
        "international": expected_international,
        "normalised_to": expected_normalised,
        "phone_prefix": expected_prefix,
        "rate_multiplier": expected_rate_multiplier,
    }


@pytest.mark.parametrize(
    "recipient, expected_recipient_normalised",
    [
        ("02077091001", "442077091001"),  # UK
        ("+442077091002", "442077091002"),  # UK
        ("020 7709 1000", "442077091000"),  # UK
    ],
)
def test_validate_and_format_recipient_gets_correct_info_for_landline_numbers(
    sample_job,
    recipient,
    expected_recipient_normalised,
):
    sample_job.service.permissions = [
        ServicePermission(service_id=sample_job.service.id, permission=SMS_TYPE),
        ServicePermission(service_id=sample_job.service.id, permission=SMS_TO_UK_LANDLINES),
    ]

    result = validate_and_format_recipient(recipient, KEY_TYPE_NORMAL, sample_job.service, SMS_TYPE)
    assert result == {
        "unformatted_recipient": recipient,
        "international": False,
        "normalised_to": expected_recipient_normalised,
        "phone_prefix": "44",
        "rate_multiplier": 1,
    }


@pytest.mark.parametrize(
    "recipient, expected_recipient_normalised",
    [
        ("7900900123", "447900900123"),  # uk number adding country code correctly
        (
            "+447900   900 123",
            "447900900123",
        ),  # uk number stripping whitespace and leading plus
        (
            "  07700900222",
            "447700900222",
        ),  # uk number stripping whitespace and adding country code
        (
            "07700900222",
            "447700900222",
        ),  # uk number stripping leading zero and adding country code
        (" 74952122020", "74952122020"),  # russian number that looks like a uk mobile
        (
            "36705450911",
            "36705450911",
        ),  # hungarian number to test international numbers
        ("-077-00900222-", "447700900222"),  # uk mobile test stripping hyphens
        (
            "(3670545(0911))",
            "36705450911",
        ),  # hungarian number to test international numbers (stripping brackets)
    ],
)
def test_validate_and_format_recipient_normalises_numbers(sample_job, recipient, expected_recipient_normalised):
    result = validate_and_format_recipient(recipient, KEY_TYPE_NORMAL, sample_job.service, SMS_TYPE)
    assert result["normalised_to"] == expected_recipient_normalised


def test_validate_and_format_recipient_without_send_to_landline_permission_raises_InvalidPhoneError(
    sample_service, sample_sms_template
):
    recipient = "+442077091002"
    sample_sms_template.service.permissions = [
        ServicePermission(service_id=sample_sms_template.service_id, permission=SMS_TYPE),
    ]
    with pytest.raises(InvalidPhoneError):
        validate_and_format_recipient(recipient, KEY_TYPE_NORMAL, sample_service, SMS_TYPE)


def test_validate_and_format_recipient_fails_when_no_recipient():
    with pytest.raises(BadRequestError) as e:
        validate_and_format_recipient(None, "key_type", "service", "SMS_TYPE")
    assert e.value.status_code == 400
    assert e.value.message == "Recipient can't be empty"


def test_check_service_email_reply_to_where_email_reply_to_is_found(sample_service):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    assert check_service_email_reply_to_id(sample_service.id, reply_to_address.id, EMAIL_TYPE) == "test@test.com"


def test_check_service_email_reply_to_id_where_service_id_is_not_found(sample_service, fake_uuid):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(fake_uuid, reply_to_address.id, EMAIL_TYPE)
    assert e.value.status_code == 400
    assert (
        e.value.message
        == f"email_reply_to_id {reply_to_address.id} does not exist in database for service id {fake_uuid}"
    )


def test_check_service_email_reply_to_id_where_reply_to_id_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(sample_service.id, fake_uuid, EMAIL_TYPE)
    assert e.value.status_code == 400
    assert (
        e.value.message
        == f"email_reply_to_id {fake_uuid} does not exist in database for service id {sample_service.id}"
    )


def test_check_service_sms_sender_id_where_sms_sender_id_is_found(sample_service):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    assert check_service_sms_sender_id(sample_service.id, sms_sender.id, SMS_TYPE) == "123456"


def test_check_service_sms_sender_id_where_service_id_is_not_found(sample_service, fake_uuid):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    with pytest.raises(BadRequestError) as e:
        check_service_sms_sender_id(fake_uuid, sms_sender.id, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == f"sms_sender_id {sms_sender.id} does not exist in database for service id {fake_uuid}"


def test_check_service_sms_sender_id_where_sms_sender_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_sms_sender_id(sample_service.id, fake_uuid, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == f"sms_sender_id {fake_uuid} does not exist in database for service id {sample_service.id}"


def test_check_service_letter_contact_id_where_letter_contact_id_is_found(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block="123456")
    assert check_service_letter_contact_id(sample_service.id, letter_contact.id, LETTER_TYPE) == "123456"


def test_check_service_letter_contact_id_where_service_id_is_not_found(sample_service, fake_uuid):
    letter_contact = create_letter_contact(service=sample_service, contact_block="123456")
    with pytest.raises(BadRequestError) as e:
        check_service_letter_contact_id(fake_uuid, letter_contact.id, LETTER_TYPE)
    assert e.value.status_code == 400
    assert (
        e.value.message
        == f"letter_contact_id {letter_contact.id} does not exist in database for service id {fake_uuid}"
    )


def test_check_service_letter_contact_id_where_letter_contact_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_letter_contact_id(sample_service.id, fake_uuid, LETTER_TYPE)
    assert e.value.status_code == 400
    assert (
        e.value.message
        == f"letter_contact_id {fake_uuid} does not exist in database for service id {sample_service.id}"
    )


@pytest.mark.parametrize(
    "func",
    [check_service_email_reply_to_id, check_service_sms_sender_id, check_service_letter_contact_id],
)
@pytest.mark.parametrize(
    "notification_type",
    ["sms", "email", "letter"],
)
def test_check_reply_to_with_empty_reply_to(sample_service, notification_type, func):
    assert func(None, None, notification_type) is None
    assert func(sample_service.id, None, notification_type) is None


def test_check_reply_to_email_type(sample_service):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    assert check_service_email_reply_to_id(sample_service.id, reply_to_address.id, EMAIL_TYPE) == "test@test.com"


def test_check_reply_to_sms_type(sample_service):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    assert check_service_sms_sender_id(sample_service.id, sms_sender.id, SMS_TYPE) == "123456"


def test_check_reply_to_letter_type(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block="123456")
    assert check_service_letter_contact_id(sample_service.id, letter_contact.id, LETTER_TYPE) == "123456"


def test_check_if_service_can_send_files_by_email_raises_if_no_contact_link_set(sample_service, hostnames):
    with pytest.raises(BadRequestError) as e:
        check_if_service_can_send_files_by_email(
            service_contact_link=sample_service.contact_link, service_id=sample_service.id
        )

    message = (
        f"Send files by email has not been set up - add contact details for your service at "
        f"{hostnames.admin}/services/{sample_service.id}/service-settings/send-files-by-email"
    )
    assert e.value.status_code == 400
    assert e.value.message == message


def test_check_if_service_can_send_files_by_email_passes_if_contact_link_set(sample_service):
    sample_service.contact_link = "contact.me@gov.uk"
    check_if_service_can_send_files_by_email(
        service_contact_link=sample_service.contact_link, service_id=sample_service.id
    )


@pytest.mark.parametrize(
    "key, address_line_3, expected_postage",
    [
        ("address_line_3", "SW1 1AA", None),
        ("address_line_5", "CANADA", "rest-of-world"),
        ("address_line_3", "GERMANY", "europe"),
    ],
)
def test_validate_address(notify_db_session, key, address_line_3, expected_postage):
    service = create_service(service_permissions=[LETTER_TYPE, INTERNATIONAL_LETTERS])
    data = {
        "address_line_1": "Prince Harry",
        "address_line_2": "Toronto",
        key: address_line_3,
    }
    postage = validate_address(service, data)
    assert postage == expected_postage


def test_validate_address_international_bfpo_error(notify_db_session):
    service = create_service(service_permissions=[LETTER_TYPE, INTERNATIONAL_LETTERS])
    data = {
        "address_line_1": "Test User",
        "address_line_2": "Abroad",
        "address_line_3": "BFPO 1234",
        "address_line_4": "USA",
    }
    with pytest.raises(ValidationError) as e:
        validate_address(service, data)

    assert e.value.message == "The last line of a BFPO address must not be a country."
