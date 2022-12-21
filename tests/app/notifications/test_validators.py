import pytest
from flask import current_app
from freezegun import freeze_time
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.clients.redis import daily_limit_cache_key

import app
from app.dao import templates_dao
from app.models import EMAIL_TYPE, INTERNATIONAL_LETTERS, LETTER_TYPE, SMS_TYPE
from app.notifications.process_notifications import (
    create_content_for_notification,
)
from app.notifications.validators import (
    check_if_service_can_send_files_by_email,
    check_is_message_too_long,
    check_notification_content_is_not_empty,
    check_rate_limiting,
    check_reply_to,
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
from app.v2.errors import BadRequestError, RateLimitError, TooManyRequestsError
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


@pytest.mark.parametrize("key_type", ["team", "normal"])
@pytest.mark.parametrize("notification_type", [None])
def test_check_service_message_limit_in_cache_under_message_limit_passes(
    key_type, sample_service, mocker, notification_type
):
    serialised_service = SerialisedService.from_id(sample_service.id)
    mock_get = mocker.patch("app.notifications.validators.redis_store.get", return_value="1")
    mock_set = mocker.patch("app.notifications.validators.redis_store.set")
    service_stats = check_service_over_daily_message_limit(
        serialised_service, key_type, notification_type=notification_type
    )
    assert service_stats == 1
    mock_get.assert_called_once_with(daily_limit_cache_key(sample_service.id, notification_type=notification_type))
    mock_set.assert_not_called()


@pytest.mark.parametrize("notification_type", [None])
def test_check_service_over_daily_message_limit_should_not_interact_with_cache_for_test_key(
    sample_service, mocker, notification_type
):
    mocker.patch("app.notifications.validators.redis_store")
    mock_get = mocker.patch("app.notifications.validators.redis_store.get", side_effect=[None])
    serialised_service = SerialisedService.from_id(sample_service.id)
    service_stats = check_service_over_daily_message_limit(
        serialised_service, "test", notification_type=notification_type
    )
    assert service_stats == 0
    mock_get.assert_not_called()


@pytest.mark.parametrize("key_type", ["team", "normal"])
@pytest.mark.parametrize("notification_type", [None])
def test_check_service_over_daily_message_limit_should_set_cache_value_as_zero_if_cache_not_set(
    key_type, sample_template, sample_service, mocker, notification_type
):
    serialised_service = SerialisedService.from_id(sample_service.id)
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch("app.notifications.validators.redis_store.set")
        service_stats = check_service_over_daily_message_limit(
            serialised_service, key_type, notification_type=notification_type
        )
        app.notifications.validators.redis_store.set.assert_called_with(
            daily_limit_cache_key(sample_service.id, notification_type=notification_type), 0, ex=86400
        )
        assert service_stats == 0


@pytest.mark.parametrize("notification_type", [None])
def test_check_service_over_daily_message_limit_does_nothing_if_redis_disabled(
    notify_api, sample_service, mocker, notification_type
):
    serialised_service = SerialisedService.from_id(sample_service.id)
    with set_config(notify_api, "REDIS_ENABLED", False):
        mock_cache_key = mocker.patch("notifications_utils.clients.redis.daily_limit_cache_key")
        service_stats = check_service_over_daily_message_limit(
            serialised_service, "normal", notification_type=notification_type
        )
        assert service_stats == 0
        assert mock_cache_key.method_calls == []


@pytest.mark.parametrize("key_type", ["team", "normal"])
@pytest.mark.parametrize("notification_type", [None])
def test_check_service_message_limit_over_message_limit_fails(key_type, mocker, notify_db_session, notification_type):
    service = create_service(message_limit=4, email_message_limit=4, letter_message_limit=4, sms_message_limit=4)
    mocker.patch("app.redis_store.get", return_value="5")

    with pytest.raises(TooManyRequestsError) as e:
        check_service_over_daily_message_limit(service, key_type, notification_type=notification_type)
    assert e.value.status_code == 429
    if notification_type is None:
        assert e.value.message == "Exceeded send limits (total: 4) for today"
    else:
        assert e.value.message == f"Exceeded send limits ({notification_type}: 4) for today"
    assert e.value.fields == []


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
    error_message = "{0} template is not suitable for {1} notification".format(template_type, notification_type)
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
            "Can’t send to this recipient when service is in trial mode – see https://www.notifications.service.gov.uk/trial-mode",  # noqa
        ),
    ],
)  # noqa
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
    template_with_content.values
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


def test_validate_template_calls_all_validators_exception_message_too_long(mocker, fake_uuid, sample_service):
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
def test_check_service_over_api_rate_limit_when_exceed_rate_limit_request_fails_raises_error(
    key_type, sample_service, mocker
):
    with freeze_time("2016-01-01 12:00:00.000000"):

        if key_type == "live":
            api_key_type = "normal"
        else:
            api_key_type = key_type

        mocker.patch("app.redis_store.exceeded_rate_limit", return_value=True)

        sample_service.restricted = True
        api_key = create_api_key(sample_service, key_type=api_key_type)
        serialised_service = SerialisedService.from_id(sample_service.id)
        serialised_api_key = SerialisedAPIKeyCollection.from_service_id(serialised_service.id)[0]

        with pytest.raises(RateLimitError) as e:
            check_service_over_api_rate_limit(serialised_service, serialised_api_key.key_type)

        assert app.redis_store.exceeded_rate_limit.called_with(
            "{}-{}".format(str(sample_service.id), api_key.key_type), sample_service.rate_limit, 60
        )
        assert e.value.status_code == 429
        assert e.value.message == "Exceeded rate limit for key type {} of {} requests per {} seconds".format(
            key_type.upper(), sample_service.rate_limit, 60
        )
        assert e.value.fields == []


def test_check_service_over_api_rate_limit_when_rate_limit_has_not_exceeded_limit_succeeds(sample_service, mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch("app.redis_store.exceeded_rate_limit", return_value=False)

        sample_service.restricted = True
        api_key = create_api_key(sample_service)
        serialised_service = SerialisedService.from_id(sample_service.id)
        serialised_api_key = SerialisedAPIKeyCollection.from_service_id(serialised_service.id)[0]

        check_service_over_api_rate_limit(serialised_service, serialised_api_key.key_type)
        assert app.redis_store.exceeded_rate_limit.called_with(
            "{}-{}".format(str(sample_service.id), api_key.key_type), 3000, 60
        )


def test_check_service_over_api_rate_limit_should_do_nothing_if_limiting_is_disabled(sample_service, mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        current_app.config["API_RATE_LIMIT_ENABLED"] = False

        mocker.patch("app.redis_store.exceeded_rate_limit", return_value=False)

        sample_service.restricted = True
        create_api_key(sample_service)
        serialised_service = SerialisedService.from_id(sample_service.id)
        serialised_api_key = SerialisedAPIKeyCollection.from_service_id(serialised_service.id)[0]

        check_service_over_api_rate_limit(serialised_service, serialised_api_key.key_type)
        app.redis_store.exceeded_rate_limit.assert_not_called()


@pytest.mark.parametrize("notification_type", [None])
def test_check_rate_limiting_validates_api_rate_limit_and_daily_limit(notify_db_session, mocker, notification_type):
    mock_rate_limit = mocker.patch("app.notifications.validators.check_service_over_api_rate_limit")
    mock_daily_limit = mocker.patch("app.notifications.validators.check_service_over_daily_message_limit")
    service = create_service()
    api_key = create_api_key(service=service)

    check_rate_limiting(service, api_key, notification_type=notification_type)

    mock_rate_limit.assert_called_once_with(service, api_key.key_type)
    mock_daily_limit.assert_called_once_with(service, api_key.key_type, notification_type=None)
    mock_daily_limit.assert_called_once_with(service, api_key.key_type, notification_type=None)


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


@pytest.mark.parametrize("key_type", ["test", "normal"])
def test_validate_and_format_recipient_succeeds_with_international_numbers_if_service_does_allow_int_sms(
    key_type, sample_service_full_permissions
):
    service_model = SerialisedService.from_id(sample_service_full_permissions.id)
    result = validate_and_format_recipient("20-12-1234-1234", key_type, service_model, SMS_TYPE)
    assert result == "201212341234"


def test_validate_and_format_recipient_fails_when_no_recipient():
    with pytest.raises(BadRequestError) as e:
        validate_and_format_recipient(None, "key_type", "service", "SMS_TYPE")
    assert e.value.status_code == 400
    assert e.value.message == "Recipient can't be empty"


@pytest.mark.parametrize("notification_type", ["sms", "email", "letter"])
def test_check_service_email_reply_to_id_where_reply_to_id_is_none(notification_type):
    assert check_service_email_reply_to_id(None, None, notification_type) is None


def test_check_service_email_reply_to_where_email_reply_to_is_found(sample_service):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    assert check_service_email_reply_to_id(sample_service.id, reply_to_address.id, EMAIL_TYPE) == "test@test.com"


def test_check_service_email_reply_to_id_where_service_id_is_not_found(sample_service, fake_uuid):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(fake_uuid, reply_to_address.id, EMAIL_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == "email_reply_to_id {} does not exist in database for service id {}".format(
        reply_to_address.id, fake_uuid
    )


def test_check_service_email_reply_to_id_where_reply_to_id_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(sample_service.id, fake_uuid, EMAIL_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == "email_reply_to_id {} does not exist in database for service id {}".format(
        fake_uuid, sample_service.id
    )


@pytest.mark.parametrize("notification_type", ["sms", "email", "letter"])
def test_check_service_sms_sender_id_where_sms_sender_id_is_none(notification_type):
    assert check_service_sms_sender_id(None, None, notification_type) is None


def test_check_service_sms_sender_id_where_sms_sender_id_is_found(sample_service):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    assert check_service_sms_sender_id(sample_service.id, sms_sender.id, SMS_TYPE) == "123456"


def test_check_service_sms_sender_id_where_service_id_is_not_found(sample_service, fake_uuid):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    with pytest.raises(BadRequestError) as e:
        check_service_sms_sender_id(fake_uuid, sms_sender.id, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == "sms_sender_id {} does not exist in database for service id {}".format(
        sms_sender.id, fake_uuid
    )


def test_check_service_sms_sender_id_where_sms_sender_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_sms_sender_id(sample_service.id, fake_uuid, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == "sms_sender_id {} does not exist in database for service id {}".format(
        fake_uuid, sample_service.id
    )


def test_check_service_letter_contact_id_where_letter_contact_id_is_none():
    assert check_service_letter_contact_id(None, None, "letter") is None


def test_check_service_letter_contact_id_where_letter_contact_id_is_found(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block="123456")
    assert check_service_letter_contact_id(sample_service.id, letter_contact.id, LETTER_TYPE) == "123456"


def test_check_service_letter_contact_id_where_service_id_is_not_found(sample_service, fake_uuid):
    letter_contact = create_letter_contact(service=sample_service, contact_block="123456")
    with pytest.raises(BadRequestError) as e:
        check_service_letter_contact_id(fake_uuid, letter_contact.id, LETTER_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == "letter_contact_id {} does not exist in database for service id {}".format(
        letter_contact.id, fake_uuid
    )


def test_check_service_letter_contact_id_where_letter_contact_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_letter_contact_id(sample_service.id, fake_uuid, LETTER_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == "letter_contact_id {} does not exist in database for service id {}".format(
        fake_uuid, sample_service.id
    )


@pytest.mark.parametrize("notification_type", ["sms", "email", "letter"])
def test_check_reply_to_with_empty_reply_to(sample_service, notification_type):
    assert check_reply_to(sample_service.id, None, notification_type) is None


def test_check_reply_to_email_type(sample_service):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    assert check_reply_to(sample_service.id, reply_to_address.id, EMAIL_TYPE) == "test@test.com"


def test_check_reply_to_sms_type(sample_service):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    assert check_reply_to(sample_service.id, sms_sender.id, SMS_TYPE) == "123456"


def test_check_reply_to_letter_type(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block="123456")
    assert check_reply_to(sample_service.id, letter_contact.id, LETTER_TYPE) == "123456"


def test_check_if_service_can_send_files_by_email_raises_if_no_contact_link_set(sample_service):
    with pytest.raises(BadRequestError) as e:
        check_if_service_can_send_files_by_email(
            service_contact_link=sample_service.contact_link, service_id=sample_service.id
        )

    message = (
        f"Send files by email has not been set up - add contact details for your service at "
        f"http://localhost:6012/services/{sample_service.id}/service-settings/send-files-by-email"
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
