import json
import uuid
from collections import namedtuple
from datetime import datetime, timedelta
from unittest.mock import ANY, call

import pytest
from flask import current_app
from freezegun import freeze_time
from requests import HTTPError

import app
from app import firetext_client, mmg_client, notification_provider_clients
from app.constants import (
    BRANDING_BOTH,
    BRANDING_ORG,
    BRANDING_ORG_BANNER,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    SMS_PROVIDER_ERROR_INTERVAL,
    SMS_PROVIDER_ERROR_THRESHOLD,
)
from app.dao import notifications_dao
from app.dao.provider_details_dao import get_provider_details_by_identifier
from app.delivery import send_to_providers
from app.delivery.send_to_providers import get_html_email_options, get_logo_url
from app.exceptions import NotificationTechnicalFailureException
from app.models import EmailBranding, Notification
from app.serialised_models import SerialisedService
from app.utils import parse_and_format_phone_number
from tests.app.db import (
    create_email_branding,
    create_notification,
    create_reply_to_email,
    create_service,
    create_service_sms_sender,
    create_service_with_defined_sms_sender,
    create_template,
)


def setup_function(_function):
    # pytest will run this function before each test. It makes sure the
    # state of the cache is not shared between tests.
    send_to_providers.provider_cache.clear()


def test_provider_to_use_should_return_random_provider(mocker, notify_db_session):
    mmg = get_provider_details_by_identifier("mmg")
    firetext = get_provider_details_by_identifier("firetext")
    mmg.priority = 25
    firetext.priority = 75
    mock_choices = mocker.patch("app.delivery.send_to_providers.random.choices", return_value=[mmg])

    ret = send_to_providers.provider_to_use("sms", international=False)

    mock_choices.assert_called_once_with([mmg, firetext], weights=[25, 75])
    assert ret.name == "mmg"


def test_provider_to_use_should_cache_repeated_calls(mocker, notify_db_session):
    mock_choices = mocker.patch(
        "app.delivery.send_to_providers.random.choices",
        wraps=send_to_providers.random.choices,
    )

    results = [send_to_providers.provider_to_use("sms", international=False) for _ in range(10)]

    assert all(result == results[0] for result in results)
    assert len(mock_choices.call_args_list) == 1


@pytest.mark.parametrize(
    "international_provider_priority",
    (
        # Since there’s only one international provider it should always
        # be used, no matter what its priority is set to
        0,
        50,
        100,
    ),
)
def test_provider_to_use_should_only_return_mmg_for_international(
    mocker,
    notify_db_session,
    international_provider_priority,
):
    mmg = get_provider_details_by_identifier("mmg")
    mmg.priority = international_provider_priority
    mock_choices = mocker.patch("app.delivery.send_to_providers.random.choices", return_value=[mmg])

    ret = send_to_providers.provider_to_use("sms", international=True)

    mock_choices.assert_called_once_with([mmg], weights=[100])
    assert ret.name == "mmg"


def test_provider_to_use_should_only_return_active_providers(mocker, restore_provider_details):
    mmg = get_provider_details_by_identifier("mmg")
    firetext = get_provider_details_by_identifier("firetext")
    mmg.active = False
    mock_choices = mocker.patch("app.delivery.send_to_providers.random.choices", return_value=[firetext])

    ret = send_to_providers.provider_to_use("sms")

    mock_choices.assert_called_once_with([firetext], weights=[100])
    assert ret.name == "firetext"


def test_provider_to_use_raises_if_no_active_providers(mocker, restore_provider_details):
    mmg = get_provider_details_by_identifier("mmg")
    mmg.active = False

    with pytest.raises(Exception):  # noqa
        send_to_providers.provider_to_use("sms", international=True)


def test_should_send_personalised_template_to_correct_sms_provider_and_persist(sample_sms_template_with_html, mocker):
    db_notification = create_notification(
        template=sample_sms_template_with_html,
        to_field="+447234123123",
        personalisation={"name": "Jo"},
        status="created",
        reply_to_text=sample_sms_template_with_html.service.get_default_sms_sender(),
        normalised_to="447234123123",
    )

    mocker.patch("app.mmg_client.send_sms")

    send_to_providers.send_sms_to_provider(db_notification)

    mmg_client.send_sms.assert_called_once_with(
        to="447234123123",
        content="Hello Jo\nHere is <em>some HTML</em> & entities",
        reference=str(db_notification.id),
        sender=current_app.config["FROM_NUMBER"],
        international=False,
    )

    notification = Notification.query.filter_by(id=db_notification.id).one()

    assert notification.status == "sending"
    assert notification.sent_at <= datetime.utcnow()
    assert notification.sent_by == "mmg"
    assert notification.billable_units == 1
    assert notification.personalisation == {"name": "Jo"}


def test_should_send_personalised_template_to_correct_email_provider_and_persist(
    sample_email_template_with_html, mocker
):
    db_notification = create_notification(
        template=sample_email_template_with_html,
        to_field="jo.smith@example.com",
        personalisation={"name": "Jo"},
        normalised_to="jo.smith@example.com",
    )

    mocker.patch("app.aws_ses_client.send_email", return_value="reference")

    send_to_providers.send_email_to_provider(db_notification)

    app.aws_ses_client.send_email.assert_called_once_with(
        from_address='"Sample service" <sample.service@test.notify.com>',
        to_address="jo.smith@example.com",
        subject="Jo <em>some HTML</em>",
        body="Hello Jo\nThis is an email from GOV.\u200bUK with <em>some HTML</em>\n",
        html_body=ANY,
        headers=[],
        reply_to_address=None,
    )

    assert "<!DOCTYPE html" in app.aws_ses_client.send_email.call_args[1]["html_body"]
    assert "&lt;em&gt;some HTML&lt;/em&gt;" in app.aws_ses_client.send_email.call_args[1]["html_body"]

    notification = Notification.query.filter_by(id=db_notification.id).one()
    assert notification.status == "sending"
    assert notification.sent_at <= datetime.utcnow()
    assert notification.sent_by == "ses"
    assert notification.personalisation == {"name": "Jo"}


def test_should_not_send_email_message_when_service_is_inactive_notifcation_is_in_tech_failure(
    sample_service, sample_notification, mocker
):
    sample_service.active = False
    send_mock = mocker.patch("app.aws_ses_client.send_email", return_value="reference")

    with pytest.raises(NotificationTechnicalFailureException) as e:
        send_to_providers.send_email_to_provider(sample_notification)
    assert str(sample_notification.id) in str(e.value)
    send_mock.assert_not_called()
    assert Notification.query.get(sample_notification.id).status == "technical-failure"


@pytest.mark.parametrize("client_send", ["app.mmg_client.send_sms", "app.firetext_client.send_sms"])
def test_should_not_send_sms_message_when_service_is_inactive_notification_is_in_tech_failure(
    sample_service, sample_notification, mocker, client_send
):
    sample_service.active = False
    send_mock = mocker.patch(client_send, return_value="reference")

    with pytest.raises(NotificationTechnicalFailureException) as e:
        send_to_providers.send_sms_to_provider(sample_notification)
    assert str(sample_notification.id) in str(e.value)
    send_mock.assert_not_called()
    assert Notification.query.get(sample_notification.id).status == "technical-failure"


def test_send_sms_should_use_template_version_from_notification_not_latest(sample_template, mocker):
    db_notification = create_notification(
        template=sample_template,
        to_field="+447234123123",
        status="created",
        reply_to_text=sample_template.service.get_default_sms_sender(),
        normalised_to="447234123123",
    )

    mocker.patch("app.mmg_client.send_sms")

    version_on_notification = sample_template.version
    expected_template_id = sample_template.id

    # Change the template
    from app.dao.templates_dao import (
        dao_get_template_by_id,
        dao_update_template,
    )

    sample_template.content = sample_template.content + " another version of the template"
    dao_update_template(sample_template)
    t = dao_get_template_by_id(sample_template.id)
    assert t.version > version_on_notification

    send_to_providers.send_sms_to_provider(db_notification)

    mmg_client.send_sms.assert_called_once_with(
        to=parse_and_format_phone_number("+447234123123"),
        content="Sample service: This is a template:\nwith a newline",
        reference=str(db_notification.id),
        sender=current_app.config["FROM_NUMBER"],
        international=False,
    )

    t = dao_get_template_by_id(expected_template_id)

    persisted_notification = notifications_dao.get_notification_by_id(db_notification.id)
    assert persisted_notification.to == db_notification.to
    assert persisted_notification.template_id == expected_template_id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.template_version != t.version
    assert persisted_notification.status == "sending"
    assert not persisted_notification.personalisation


def test_should_call_send_sms_response_task_if_test_api_key(notify_db_session, sample_notification, mocker):
    mocker.patch("app.mmg_client.send_sms")
    mocker.patch("app.delivery.send_to_providers.send_sms_response")

    sample_notification.key_type = KEY_TYPE_TEST

    send_to_providers.send_sms_to_provider(sample_notification)
    assert not mmg_client.send_sms.called

    app.delivery.send_to_providers.send_sms_response.assert_called_once_with(
        "mmg", str(sample_notification.id), sample_notification.to
    )

    persisted_notification = notifications_dao.get_notification_by_id(sample_notification.id)
    assert persisted_notification.to == sample_notification.to
    assert persisted_notification.template_id == sample_notification.template_id
    assert persisted_notification.status == "sending"
    assert persisted_notification.sent_at <= datetime.utcnow()
    assert persisted_notification.sent_by == "mmg"
    assert not persisted_notification.personalisation


def test_should_have_sending_status_if_fake_callback_function_fails(sample_notification, mocker):
    mocker.patch("app.delivery.send_to_providers.send_sms_response", side_effect=HTTPError)

    sample_notification.key_type = KEY_TYPE_TEST

    with pytest.raises(HTTPError):
        send_to_providers.send_sms_to_provider(sample_notification)
    assert sample_notification.status == "sending"
    assert sample_notification.sent_by == "mmg"


def test_should_not_send_to_provider_when_status_is_not_created(sample_template, mocker):
    notification = create_notification(template=sample_template, status="sending")
    mocker.patch("app.mmg_client.send_sms")
    response_mock = mocker.patch("app.delivery.send_to_providers.send_sms_response")

    send_to_providers.send_sms_to_provider(notification)

    app.mmg_client.send_sms.assert_not_called()
    response_mock.assert_not_called()


def test_should_send_sms_with_downgraded_content(notify_db_session, mocker):
    # é, o, and u are in GSM.
    # ī, grapes, tabs, zero width space and ellipsis are not
    # ó isn't in GSM, but it is in the welsh alphabet so will still be sent
    msg = "a é ī o u 🍇 foo\tbar\u200bbaz((misc))…"
    placeholder = "∆∆∆abc"
    gsm_message = "Lódz Housing Service: a é i o u ? foo barbaz???abc..."
    service = create_service(service_name="Łódź Housing Service")
    template = create_template(service, content=msg)
    db_notification = create_notification(template=template, personalisation={"misc": placeholder})

    mocker.patch("app.mmg_client.send_sms")

    send_to_providers.send_sms_to_provider(db_notification)

    mmg_client.send_sms.assert_called_once_with(
        to=ANY, content=gsm_message, reference=ANY, sender=ANY, international=False
    )


def test_send_sms_should_use_service_sms_sender(sample_service, sample_template, mocker):
    mocker.patch("app.mmg_client.send_sms")

    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456", is_default=False)
    db_notification = create_notification(template=sample_template, reply_to_text=sms_sender.sms_sender)
    expected_sender_name = sms_sender.sms_sender

    send_to_providers.send_sms_to_provider(
        db_notification,
    )

    app.mmg_client.send_sms.assert_called_once_with(
        to=ANY, content=ANY, reference=ANY, sender=expected_sender_name, international=False
    )


def test_send_email_to_provider_should_call_response_task_if_test_key(sample_email_template, mocker):
    notification = create_notification(
        template=sample_email_template, to_field="john@smith.com", key_type=KEY_TYPE_TEST, billable_units=0
    )

    reference = uuid.uuid4()
    mocker.patch("app.uuid.uuid4", return_value=reference)
    mocker.patch("app.aws_ses_client.send_email")
    mocker.patch("app.delivery.send_to_providers.send_email_response")

    send_to_providers.send_email_to_provider(notification)

    assert not app.aws_ses_client.send_email.called
    app.delivery.send_to_providers.send_email_response.assert_called_once_with(str(reference), "john@smith.com")
    persisted_notification = Notification.query.filter_by(id=notification.id).one()
    assert persisted_notification.to == "john@smith.com"
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.status == "sending"
    assert persisted_notification.sent_at <= datetime.utcnow()
    assert persisted_notification.created_at <= datetime.utcnow()
    assert persisted_notification.sent_by == "ses"
    assert persisted_notification.reference == str(reference)
    assert persisted_notification.billable_units == 0


def test_send_email_to_provider_should_not_send_to_provider_when_status_is_not_created(sample_email_template, mocker):
    notification = create_notification(template=sample_email_template, status="sending")
    mocker.patch("app.aws_ses_client.send_email")
    mocker.patch("app.delivery.send_to_providers.send_email_response")

    send_to_providers.send_sms_to_provider(notification)
    app.aws_ses_client.send_email.assert_not_called()
    app.delivery.send_to_providers.send_email_response.assert_not_called()


def test_send_email_should_use_service_reply_to_email(sample_service, sample_email_template, mocker):
    mocker.patch("app.aws_ses_client.send_email", return_value="reference")

    db_notification = create_notification(template=sample_email_template, reply_to_text="foo@bar.com")
    create_reply_to_email(service=sample_service, email_address="foo@bar.com")

    send_to_providers.send_email_to_provider(
        db_notification,
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        from_address=ANY,
        to_address=ANY,
        subject=ANY,
        body=ANY,
        html_body=ANY,
        headers=[],
        reply_to_address="foo@bar.com",
    )


@pytest.mark.parametrize("service_fixture", ["sample_service", "sample_service_with_email_branding"])
def test_send_email_works_with_and_without_email_branding(request, service_fixture, sample_email_template, mocker):
    request.getfixturevalue(service_fixture)  # Creates and loads the relevant service fixture into the DB
    mocker.patch("app.aws_ses_client.send_email", return_value="reference")

    db_notification = create_notification(template=sample_email_template, reply_to_text="foo@bar.com")

    send_to_providers.send_email_to_provider(
        db_notification,
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        from_address=ANY,
        to_address=ANY,
        subject=ANY,
        body=ANY,
        html_body=ANY,
        headers=[],
        reply_to_address="foo@bar.com",
    )


def test_get_html_email_renderer_should_return_for_normal_service(sample_service):
    options = send_to_providers.get_html_email_options(sample_service)
    assert options["govuk_banner"] is True
    assert "brand_colour" not in options.keys()
    assert "brand_logo" not in options.keys()
    assert "brand_text" not in options.keys()
    assert "brand_alt_text" not in options.keys()


@pytest.mark.parametrize(
    "branding_type, govuk_banner", [(BRANDING_ORG, False), (BRANDING_BOTH, True), (BRANDING_ORG_BANNER, False)]
)
def test_get_html_email_renderer_with_branding_details(branding_type, govuk_banner, notify_db_session, sample_service):
    email_branding = EmailBranding(
        brand_type=branding_type,
        colour="#000000",
        logo="justice-league.png",
        name="Justice League",
        text="League of Justice",
    )
    sample_service.email_branding = email_branding
    notify_db_session.add_all([sample_service, email_branding])
    notify_db_session.commit()

    options = send_to_providers.get_html_email_options(sample_service)

    assert options["govuk_banner"] == govuk_banner
    assert options["brand_colour"] == "#000000"
    assert options["brand_text"] == "League of Justice"
    assert options["brand_alt_text"] is None

    if branding_type == BRANDING_ORG_BANNER:
        assert options["brand_banner"] is True
    else:
        assert options["brand_banner"] is False


def test_get_html_email_renderer_with_branding_details_and_render_govuk_banner_only(notify_db_session, sample_service):
    sample_service.email_branding = None
    notify_db_session.add_all([sample_service])
    notify_db_session.commit()

    options = send_to_providers.get_html_email_options(sample_service)

    assert options == {"govuk_banner": True, "brand_banner": False, "rebrand": True}


def test_get_html_email_renderer_prepends_logo_path(notify_api, hostnames):
    Service = namedtuple("Service", ["email_branding"])
    EmailBranding = namedtuple("EmailBranding", ["brand_type", "colour", "name", "logo", "text", "alt_text"])

    email_branding = EmailBranding(
        brand_type=BRANDING_ORG,
        colour="#000000",
        logo="justice-league.png",
        name="Justice League",
        text="League of Justice",
        alt_text=None,
    )
    service = Service(
        email_branding=email_branding,
    )

    renderer = send_to_providers.get_html_email_options(service)

    assert renderer["brand_logo"] == "http://static-logos.notify.tools/justice-league.png"


def test_get_html_email_renderer_handles_email_branding_without_logo(notify_api):
    Service = namedtuple("Service", ["email_branding"])
    EmailBranding = namedtuple("EmailBranding", ["brand_type", "colour", "name", "logo", "text", "alt_text"])

    email_branding = EmailBranding(
        brand_type=BRANDING_ORG_BANNER,
        colour="#000000",
        logo=None,
        name="Justice League",
        text="League of Justice",
        alt_text=None,
    )
    service = Service(
        email_branding=email_branding,
    )

    renderer = send_to_providers.get_html_email_options(service)

    assert renderer["govuk_banner"] is False
    assert renderer["brand_banner"] is True
    assert renderer["brand_logo"] is None
    assert renderer["brand_text"] == "League of Justice"
    assert renderer["brand_colour"] == "#000000"
    assert renderer["brand_alt_text"] is None


@pytest.mark.parametrize(
    "base_url, expected_url",
    [
        # don't change localhost to prevent errors when testing locally
        ("http://localhost:6012", "http://static-logos.notify.tools/filename.png"),
        ("https://www.notifications.service.gov.uk", "https://static-logos.notifications.service.gov.uk/filename.png"),
        ("https://notify.works", "https://static-logos.notify.works/filename.png"),
        ("https://staging-notify.works", "https://static-logos.staging-notify.works/filename.png"),
        ("https://www.notify.works", "https://static-logos.notify.works/filename.png"),
        ("https://www.staging-notify.works", "https://static-logos.staging-notify.works/filename.png"),
    ],
)
def test_get_logo_url_works_for_different_environments(base_url, expected_url):
    logo_file = "filename.png"

    logo_url = send_to_providers.get_logo_url(base_url, logo_file)

    assert logo_url == expected_url


@pytest.mark.parametrize(
    "starting_status, expected_status",
    [
        ("delivered", "delivered"),
        ("created", "sending"),
        ("technical-failure", "technical-failure"),
    ],
)
def test_update_notification_to_sending_does_not_update_status_from_a_final_status(
    sample_service, notify_db_session, starting_status, expected_status
):
    template = create_template(sample_service)
    notification = create_notification(template=template, status=starting_status)
    send_to_providers.update_notification_to_sending(
        notification, notification_provider_clients.get_client_by_name_and_type("mmg", "sms")
    )
    assert notification.status == expected_status


def __update_notification(notification_to_update, expected_status):
    if notification_to_update.key_type == KEY_TYPE_TEST:
        notification_to_update.status = expected_status


@pytest.mark.parametrize(
    "key_type, billable_units, expected_status",
    [
        (KEY_TYPE_NORMAL, 1, "sending"),
        (KEY_TYPE_TEST, 0, "sending"),
        (KEY_TYPE_TEAM, 1, "sending"),
    ],
)
def test_should_update_billable_units_and_status_according_to_and_key_type(
    sample_template, mocker, key_type, billable_units, expected_status
):
    notification = create_notification(template=sample_template, billable_units=0, status="created", key_type=key_type)
    mocker.patch("app.mmg_client.send_sms")
    mocker.patch(
        "app.delivery.send_to_providers.send_sms_response",
        side_effect=__update_notification(notification, expected_status),
    )

    send_to_providers.send_sms_to_provider(notification)
    assert notification.billable_units == billable_units
    assert notification.status == expected_status


@freeze_time("2034-03-26 23:01")
def test_should_set_notification_billable_units_if_sending_to_provider_fails_and_error_rate_limit_not_exceeded(
    sample_notification,
    mocker,
):
    mocker.patch("app.mmg_client.send_sms", side_effect=Exception())
    mock_reduce = mocker.patch("app.delivery.send_to_providers.dao_reduce_sms_provider_priority")
    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store.exceeded_rate_limit", return_value=False)

    sample_notification.billable_units = 0
    assert sample_notification.sent_by is None

    with pytest.raises(Exception):  # noqa
        send_to_providers.send_sms_to_provider(sample_notification)

    assert sample_notification.billable_units == 1
    assert not mock_reduce.called
    mock_redis.assert_called_once_with("mmg-error-rate", SMS_PROVIDER_ERROR_THRESHOLD, SMS_PROVIDER_ERROR_INTERVAL)


@freeze_time("2034-03-26 23:01")
def test_should_set_notification_billable_units_and_reduce_provider_priority_if_sending_fails_and_error_limit_exceeded(
    sample_notification,
    mocker,
):
    mocker.patch("app.mmg_client.send_sms", side_effect=Exception())
    mock_reduce = mocker.patch("app.delivery.send_to_providers.dao_reduce_sms_provider_priority")
    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store.exceeded_rate_limit", return_value=True)

    sample_notification.billable_units = 0
    assert sample_notification.sent_by is None

    with pytest.raises(Exception):  # noqa
        send_to_providers.send_sms_to_provider(sample_notification)

    assert sample_notification.billable_units == 1
    mock_reduce.assert_called_once_with("mmg", time_threshold=timedelta(minutes=1))
    mock_redis.assert_called_once_with("mmg-error-rate", SMS_PROVIDER_ERROR_THRESHOLD, SMS_PROVIDER_ERROR_INTERVAL)


def test_should_send_sms_to_international_providers(sample_template, mocker):
    mocker.patch("app.mmg_client.send_sms")
    mocker.patch("app.firetext_client.send_sms")

    # set firetext to active
    get_provider_details_by_identifier("firetext").priority = 100
    get_provider_details_by_identifier("mmg").priority = 0

    notification_international = create_notification(
        template=sample_template,
        to_field="+6011-17224412",
        personalisation={"name": "Jo"},
        status="created",
        international=True,
        reply_to_text=sample_template.service.get_default_sms_sender(),
        normalised_to="601117224412",
    )

    send_to_providers.send_sms_to_provider(notification_international)

    mmg_client.send_sms.assert_called_once_with(
        to="601117224412",
        content=ANY,
        reference=str(notification_international.id),
        sender=current_app.config["FROM_NUMBER"],
        international=True,
    )

    assert notification_international.status == "sent"
    assert notification_international.sent_by == "mmg"


def test_should_send_non_international_sms_to_default_provider(sample_template, mocker):
    mocker.patch("app.mmg_client.send_sms")
    mocker.patch("app.firetext_client.send_sms")

    # set firetext to active
    get_provider_details_by_identifier("firetext").priority = 100
    get_provider_details_by_identifier("mmg").priority = 0

    notification_uk = create_notification(
        template=sample_template,
        to_field="+447234123999",
        personalisation={"name": "Jo"},
        status="created",
        international=False,
        reply_to_text=sample_template.service.get_default_sms_sender(),
        normalised_to="447234123999",
    )

    send_to_providers.send_sms_to_provider(notification_uk)

    firetext_client.send_sms.assert_called_once_with(
        to="447234123999",
        content=ANY,
        reference=str(notification_uk.id),
        sender=current_app.config["FROM_NUMBER"],
        international=False,
    )

    assert notification_uk.status == "sending"
    assert notification_uk.sent_by == "firetext"


@pytest.mark.parametrize(
    "sms_sender, expected_sender, prefix_sms, expected_content",
    [
        ("foo", "foo", False, "bar"),
        ("foo", "foo", True, "Sample service: bar"),
        # if 40604 is actually in DB then treat that as if entered manually
        ("40604", "40604", False, "bar"),
        # 'testing' is the FROM_NUMBER during unit tests
        ("testing", "testing", True, "Sample service: bar"),
        ("testing", "testing", False, "bar"),
    ],
)
def test_should_handle_sms_sender_and_prefix_message(
    mocker, sms_sender, prefix_sms, expected_sender, expected_content, notify_db_session
):
    mocker.patch("app.mmg_client.send_sms")
    service = create_service_with_defined_sms_sender(sms_sender_value=sms_sender, prefix_sms=prefix_sms)
    template = create_template(service, content="bar")
    notification = create_notification(template, reply_to_text=sms_sender)

    send_to_providers.send_sms_to_provider(notification)

    mmg_client.send_sms.assert_called_once_with(
        content=expected_content, sender=expected_sender, to=ANY, reference=ANY, international=False
    )


def test_send_email_to_provider_uses_reply_to_from_notification(sample_email_template, mocker):
    mocker.patch("app.aws_ses_client.send_email", return_value="reference")

    db_notification = create_notification(template=sample_email_template, reply_to_text="test@test.com")

    send_to_providers.send_email_to_provider(
        db_notification,
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        from_address=ANY,
        to_address=ANY,
        subject=ANY,
        body=ANY,
        html_body=ANY,
        headers=[],
        reply_to_address="test@test.com",
    )


def test_send_email_to_provider_uses_custom_email_sender_name_if_set(sample_email_notification, mocker):
    sample_email_notification.service.custom_email_sender_name = "Custom Sender Name"
    mocker.patch("app.aws_ses_client.send_email", return_value="reference")

    send_to_providers.send_email_to_provider(sample_email_notification)

    app.aws_ses_client.send_email.assert_called_once_with(
        from_address='"Custom Sender Name" <custom.sender.name@test.notify.com>',
        to_address=ANY,
        subject=ANY,
        body=ANY,
        html_body=ANY,
        headers=[],
        reply_to_address=ANY,
    )


def test_send_sms_to_provider_should_use_normalised_to(mocker, client, sample_template):
    send_mock = mocker.patch("app.mmg_client.send_sms")
    notification = create_notification(template=sample_template, to_field="+447700900855", normalised_to="447700900855")
    send_to_providers.send_sms_to_provider(notification)
    send_mock.assert_called_once_with(
        to=notification.normalised_to,
        content=ANY,
        reference=str(notification.id),
        sender=notification.reply_to_text,
        international=False,
    )


def test_send_email_to_provider_should_user_normalised_to(mocker, client, sample_email_template):
    send_mock = mocker.patch("app.aws_ses_client.send_email", return_value="reference")
    notification = create_notification(
        template=sample_email_template, to_field="TEST@example.com", normalised_to="test@example.com"
    )

    send_to_providers.send_email_to_provider(notification)
    send_mock.assert_called_once_with(
        from_address=ANY,
        to_address=notification.normalised_to,
        subject=ANY,
        body=ANY,
        html_body=ANY,
        headers=[],
        reply_to_address=notification.reply_to_text,
    )


def test_send_sms_to_provider_should_return_template_if_found_in_redis(mocker, client, sample_template):
    from app.schemas import service_schema, template_schema

    service_dict = service_schema.dump(sample_template.service)
    template_dict = template_schema.dump(sample_template)

    mocker.patch(
        "app.redis_store.get",
        side_effect=[
            json.dumps({"data": service_dict}).encode("utf-8"),
            json.dumps({"data": template_dict}).encode("utf-8"),
        ],
    )
    mock_get_template = mocker.patch("app.dao.templates_dao.dao_get_template_by_id_and_service_id")
    mock_get_service = mocker.patch("app.dao.services_dao.dao_fetch_service_by_id")

    send_mock = mocker.patch("app.mmg_client.send_sms")
    notification = create_notification(template=sample_template, to_field="+447700900855", normalised_to="447700900855")
    send_to_providers.send_sms_to_provider(notification)
    assert mock_get_template.called is False
    assert mock_get_service.called is False
    send_mock.assert_called_once_with(
        to=notification.normalised_to,
        content=ANY,
        reference=str(notification.id),
        sender=notification.reply_to_text,
        international=False,
    )


def test_send_email_to_provider_should_return_template_if_found_in_redis(mocker, client, sample_email_template):
    from app.schemas import service_schema, template_schema

    service_dict = service_schema.dump(sample_email_template.service)
    template_dict = template_schema.dump(sample_email_template)

    mocker.patch(
        "app.redis_store.get",
        side_effect=[
            json.dumps({"data": service_dict}).encode("utf-8"),
            json.dumps({"data": template_dict}).encode("utf-8"),
        ],
    )
    mock_get_template = mocker.patch("app.dao.templates_dao.dao_get_template_by_id_and_service_id")
    mock_get_service = mocker.patch("app.dao.services_dao.dao_fetch_service_by_id")
    send_mock = mocker.patch("app.aws_ses_client.send_email", return_value="reference")
    notification = create_notification(
        template=sample_email_template, to_field="TEST@example.com", normalised_to="test@example.com"
    )

    send_to_providers.send_email_to_provider(notification)
    assert mock_get_template.called is False
    assert mock_get_service.called is False
    send_mock.assert_called_once_with(
        from_address=ANY,
        to_address=notification.normalised_to,
        subject=ANY,
        body=ANY,
        html_body=ANY,
        headers=[],
        reply_to_address=notification.reply_to_text,
    )


def test_get_html_email_options_return_email_branding_from_serialised_service(sample_service):
    branding = create_email_branding()
    sample_service.email_branding = branding
    service = SerialisedService.from_id(sample_service.id)
    email_options = get_html_email_options(service)
    assert email_options is not None
    assert email_options == {
        "govuk_banner": branding.brand_type == BRANDING_BOTH,
        "brand_banner": branding.brand_type == BRANDING_ORG_BANNER,
        "brand_colour": branding.colour,
        "brand_logo": get_logo_url(current_app.config["ADMIN_BASE_URL"], branding.logo),
        "brand_text": branding.text,
        "brand_alt_text": branding.alt_text,
        "rebrand": True,
    }


def test_get_html_email_options_add_email_branding_from_service(sample_service):
    branding = create_email_branding()
    sample_service.email_branding = branding
    email_options = get_html_email_options(sample_service)
    assert email_options is not None
    assert email_options == {
        "govuk_banner": branding.brand_type == BRANDING_BOTH,
        "brand_banner": branding.brand_type == BRANDING_ORG_BANNER,
        "brand_colour": branding.colour,
        "brand_logo": get_logo_url(current_app.config["ADMIN_BASE_URL"], branding.logo),
        "brand_text": branding.text,
        "brand_alt_text": branding.alt_text,
        "rebrand": True,
    }


@pytest.mark.parametrize(
    "template_has_unsubscribe_link, expected_link_in_email_body",
    (
        (True, "https://www.notify.example.com"),
        (False, None),
    ),
)
def test_send_email_to_provider_sends_unsubscribe_link(
    sample_service,
    mocker,
    template_has_unsubscribe_link,
    expected_link_in_email_body,
):
    mocker.patch("app.aws_ses_client.send_email", return_value="reference")
    mock_html_email = mocker.patch("app.delivery.send_to_providers.HTMLEmailTemplate")
    mock_plain_text_email = mocker.patch("app.delivery.send_to_providers.PlainTextEmailTemplate")
    mocker.patch(
        "app.models.default.url_with_token",
        return_value="https://www.notify.example.com",
    )

    template = create_template(
        service=sample_service,
        template_type="email",
        has_unsubscribe_link=template_has_unsubscribe_link,
    )

    db_notification = create_notification(template=template, unsubscribe_link="https://example.com")

    expected_headers = [
        {"Name": "List-Unsubscribe", "Value": "<https://example.com>"},
        {"Name": "List-Unsubscribe-Post", "Value": "List-Unsubscribe=One-Click"},
    ]

    send_to_providers.send_email_to_provider(
        db_notification,
    )
    app.aws_ses_client.send_email.assert_called_once()
    assert app.aws_ses_client.send_email.call_args[1]["headers"] == expected_headers

    assert mock_html_email.call_args[1]["unsubscribe_link"] == expected_link_in_email_body
    assert mock_plain_text_email.call_args[1]["unsubscribe_link"] == expected_link_in_email_body


def test_send_email_to_provider_sends_unsubscribe_link_if_template_is_unsubscribable(sample_service, mocker):
    mocker.patch("app.aws_ses_client.send_email", return_value="reference")
    mock_url_with_token = mocker.patch(
        "app.models.default.url_with_token",
        side_effect=[
            "https://www.notify.example.com",
            "https://api.notify.example.com",
        ],
    )
    mock_html_email = mocker.patch("app.delivery.send_to_providers.HTMLEmailTemplate")
    mock_plain_text_email = mocker.patch("app.delivery.send_to_providers.PlainTextEmailTemplate")

    template = create_template(
        service=sample_service,
        template_type="email",
        has_unsubscribe_link=True,
    )

    db_notification = create_notification(template=template)

    send_to_providers.send_email_to_provider(db_notification)
    app.aws_ses_client.send_email.assert_called_once()

    assert mock_url_with_token.call_args_list == [
        call("test@example.com", url=f"/unsubscribe/{db_notification.id}/", base_url="http://localhost:6012"),
        call("test@example.com", url=f"/unsubscribe/{db_notification.id}/", base_url="http://localhost:6011"),
    ]

    assert app.aws_ses_client.send_email.call_args[1]["headers"] == [
        {"Name": "List-Unsubscribe", "Value": "<https://api.notify.example.com>"},
        {"Name": "List-Unsubscribe-Post", "Value": "List-Unsubscribe=One-Click"},
    ]

    assert mock_html_email.call_args[1]["unsubscribe_link"] == "https://www.notify.example.com"
    assert mock_plain_text_email.call_args[1]["unsubscribe_link"] == "https://www.notify.example.com"
