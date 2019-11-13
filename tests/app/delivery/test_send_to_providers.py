import uuid
from collections import namedtuple
from datetime import datetime
from unittest.mock import ANY

import pytest
from flask import current_app
from notifications_utils.recipients import validate_and_format_phone_number
from requests import HTTPError

import app
from app import mmg_client, firetext_client
from app.dao import notifications_dao
from app.dao.provider_details_dao import get_provider_details_by_identifier
from app.delivery import send_to_providers
from app.exceptions import NotificationTechnicalFailureException
from app.models import (
    Notification,
    EmailBranding,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    KEY_TYPE_TEAM,
    BRANDING_ORG,
    BRANDING_BOTH,
    BRANDING_ORG_BANNER
)
from tests.app.db import (
    create_service,
    create_template,
    create_notification,
    create_reply_to_email,
    create_service_sms_sender,
    create_service_with_defined_sms_sender
)


def test_provider_to_use_should_return_random_provider(mocker, notify_db_session):
    mmg = get_provider_details_by_identifier('mmg')
    firetext = get_provider_details_by_identifier('firetext')
    mmg.priority = 25
    firetext.priority = 75
    mock_choices = mocker.patch('app.delivery.send_to_providers.random.choices', return_value=[mmg])

    ret = send_to_providers.provider_to_use('sms', international=False)

    mock_choices.assert_called_once_with([mmg, firetext], weights=[25, 75])
    assert ret.get_name() == 'mmg'


def test_provider_to_use_should_only_return_mmg_for_international(mocker, notify_db_session):
    mmg = get_provider_details_by_identifier('mmg')
    mock_choices = mocker.patch('app.delivery.send_to_providers.random.choices', return_value=[mmg])

    ret = send_to_providers.provider_to_use('sms', international=True)

    mock_choices.assert_called_once_with([mmg], weights=[100])
    assert ret.get_name() == 'mmg'


def test_provider_to_use_should_only_return_active_providers(mocker, restore_provider_details):
    mmg = get_provider_details_by_identifier('mmg')
    firetext = get_provider_details_by_identifier('firetext')
    mmg.active = False
    mock_choices = mocker.patch('app.delivery.send_to_providers.random.choices', return_value=[firetext])

    ret = send_to_providers.provider_to_use('sms')

    mock_choices.assert_called_once_with([firetext], weights=[0])
    assert ret.get_name() == 'firetext'


def test_provider_to_use_raises_if_no_active_providers(mocker, restore_provider_details):
    mmg = get_provider_details_by_identifier('mmg')
    mmg.active = False

    with pytest.raises(Exception):
        send_to_providers.provider_to_use('sms', international=True)


def test_should_send_personalised_template_to_correct_sms_provider_and_persist(
    sample_sms_template_with_html,
    mocker
):
    db_notification = create_notification(template=sample_sms_template_with_html,
                                          to_field="+447234123123", personalisation={"name": "Jo"},
                                          status='created',
                                          reply_to_text=sample_sms_template_with_html.service.get_default_sms_sender())

    mocker.patch('app.mmg_client.send_sms')

    send_to_providers.send_sms_to_provider(
        db_notification
    )

    mmg_client.send_sms.assert_called_once_with(
        to=validate_and_format_phone_number("+447234123123"),
        content="Sample service: Hello Jo\nHere is <em>some HTML</em> & entities",
        reference=str(db_notification.id),
        sender=current_app.config['FROM_NUMBER']
    )

    notification = Notification.query.filter_by(id=db_notification.id).one()

    assert notification.status == 'sending'
    assert notification.sent_at <= datetime.utcnow()
    assert notification.sent_by == 'mmg'
    assert notification.billable_units == 1
    assert notification.personalisation == {"name": "Jo"}


def test_should_send_personalised_template_to_correct_email_provider_and_persist(
    sample_email_template_with_html,
    mocker
):
    db_notification = create_notification(
        template=sample_email_template_with_html,
        to_field="jo.smith@example.com",
        personalisation={'name': 'Jo'}
    )

    mocker.patch('app.aws_ses_client.send_email', return_value='reference')

    send_to_providers.send_email_to_provider(
        db_notification
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        '"Sample service" <sample.service@test.notify.com>',
        'jo.smith@example.com',
        'Jo <em>some HTML</em>',
        body='Hello Jo\nThis is an email from GOV.\u200bUK with <em>some HTML</em>\n',
        html_body=ANY,
        reply_to_address=None
    )

    assert '<!DOCTYPE html' in app.aws_ses_client.send_email.call_args[1]['html_body']
    assert '&lt;em&gt;some HTML&lt;/em&gt;' in app.aws_ses_client.send_email.call_args[1]['html_body']

    notification = Notification.query.filter_by(id=db_notification.id).one()
    assert notification.status == 'sending'
    assert notification.sent_at <= datetime.utcnow()
    assert notification.sent_by == 'ses'
    assert notification.personalisation == {"name": "Jo"}


def test_should_not_send_email_message_when_service_is_inactive_notifcation_is_in_tech_failure(
        sample_service, sample_notification, mocker
):
    sample_service.active = False
    send_mock = mocker.patch("app.aws_ses_client.send_email", return_value='reference')

    with pytest.raises(NotificationTechnicalFailureException) as e:
        send_to_providers.send_email_to_provider(sample_notification)
    assert str(sample_notification.id) in str(e.value)
    send_mock.assert_not_called()
    assert Notification.query.get(sample_notification.id).status == 'technical-failure'


@pytest.mark.parametrize("client_send", ["app.mmg_client.send_sms", "app.firetext_client.send_sms"])
def test_should_not_send_sms_message_when_service_is_inactive_notifcation_is_in_tech_failure(
        sample_service, sample_notification, mocker, client_send):
    sample_service.active = False
    send_mock = mocker.patch(client_send, return_value='reference')

    with pytest.raises(NotificationTechnicalFailureException) as e:
        send_to_providers.send_sms_to_provider(sample_notification)
    assert str(sample_notification.id) in str(e.value)
    send_mock.assert_not_called()
    assert Notification.query.get(sample_notification.id).status == 'technical-failure'


def test_send_sms_should_use_template_version_from_notification_not_latest(
        sample_template,
        mocker):
    db_notification = create_notification(template=sample_template, to_field='+447234123123', status='created',
                                          reply_to_text=sample_template.service.get_default_sms_sender())

    mocker.patch('app.mmg_client.send_sms')

    version_on_notification = sample_template.version

    # Change the template
    from app.dao.templates_dao import dao_update_template, dao_get_template_by_id
    sample_template.content = sample_template.content + " another version of the template"
    dao_update_template(sample_template)
    t = dao_get_template_by_id(sample_template.id)
    assert t.version > version_on_notification

    send_to_providers.send_sms_to_provider(
        db_notification
    )

    mmg_client.send_sms.assert_called_once_with(
        to=validate_and_format_phone_number("+447234123123"),
        content="Sample service: This is a template:\nwith a newline",
        reference=str(db_notification.id),
        sender=current_app.config['FROM_NUMBER']
    )

    persisted_notification = notifications_dao.get_notification_by_id(db_notification.id)
    assert persisted_notification.to == db_notification.to
    assert persisted_notification.template_id == sample_template.id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.template_version != sample_template.version
    assert persisted_notification.status == 'sending'
    assert not persisted_notification.personalisation


@pytest.mark.parametrize('research_mode,key_type', [
    (True, KEY_TYPE_NORMAL),
    (False, KEY_TYPE_TEST)
])
def test_should_call_send_sms_response_task_if_research_mode(
        notify_db, sample_service, sample_notification, mocker, research_mode, key_type
):
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.delivery.send_to_providers.send_sms_response')

    if research_mode:
        sample_service.research_mode = True
        notify_db.session.add(sample_service)
        notify_db.session.commit()

    sample_notification.key_type = key_type

    send_to_providers.send_sms_to_provider(
        sample_notification
    )
    assert not mmg_client.send_sms.called

    app.delivery.send_to_providers.send_sms_response.assert_called_once_with(
        'mmg', str(sample_notification.id), sample_notification.to
    )

    persisted_notification = notifications_dao.get_notification_by_id(sample_notification.id)
    assert persisted_notification.to == sample_notification.to
    assert persisted_notification.template_id == sample_notification.template_id
    assert persisted_notification.status == 'sending'
    assert persisted_notification.sent_at <= datetime.utcnow()
    assert persisted_notification.sent_by == 'mmg'
    assert not persisted_notification.personalisation


def test_should_have_sending_status_if_fake_callback_function_fails(sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_response', side_effect=HTTPError)

    sample_notification.key_type = KEY_TYPE_TEST

    with pytest.raises(HTTPError):
        send_to_providers.send_sms_to_provider(
            sample_notification
        )
    assert sample_notification.status == 'sending'
    assert sample_notification.sent_by == 'mmg'


def test_should_not_send_to_provider_when_status_is_not_created(
    sample_template,
    mocker
):
    notification = create_notification(template=sample_template, status='sending')
    mocker.patch('app.mmg_client.send_sms')
    response_mock = mocker.patch('app.delivery.send_to_providers.send_sms_response')

    send_to_providers.send_sms_to_provider(
        notification
    )

    app.mmg_client.send_sms.assert_not_called()
    response_mock.assert_not_called()


def test_should_send_sms_with_downgraded_content(notify_db_session, mocker):
    # é, o, and u are in GSM.
    # á, ï, grapes, tabs, zero width space and ellipsis are not
    msg = "á é ï o u 🍇 foo\tbar\u200bbaz((misc))…"
    placeholder = '∆∆∆abc'
    gsm_message = "?odz Housing Service: a é i o u ? foo barbaz???abc..."
    service = create_service(service_name='Łódź Housing Service')
    template = create_template(service, content=msg)
    db_notification = create_notification(
        template=template,
        personalisation={'misc': placeholder}
    )

    mocker.patch('app.mmg_client.send_sms')

    send_to_providers.send_sms_to_provider(db_notification)

    mmg_client.send_sms.assert_called_once_with(
        to=ANY,
        content=gsm_message,
        reference=ANY,
        sender=ANY
    )


def test_send_sms_should_use_service_sms_sender(
        sample_service,
        sample_template,
        mocker):
    mocker.patch('app.mmg_client.send_sms')

    sms_sender = create_service_sms_sender(service=sample_service, sms_sender='123456', is_default=False)
    db_notification = create_notification(template=sample_template, reply_to_text=sms_sender.sms_sender)

    send_to_providers.send_sms_to_provider(
        db_notification,
    )

    app.mmg_client.send_sms.assert_called_once_with(
        to=ANY,
        content=ANY,
        reference=ANY,
        sender=sms_sender.sms_sender
    )


@pytest.mark.parametrize('research_mode,key_type', [
    (True, KEY_TYPE_NORMAL),
    (False, KEY_TYPE_TEST)
])
def test_send_email_to_provider_should_call_research_mode_task_response_task_if_research_mode(
        sample_service,
        sample_email_template,
        mocker,
        research_mode,
        key_type):
    notification = create_notification(
        template=sample_email_template,
        to_field="john@smith.com",
        key_type=key_type,
        billable_units=0
    )
    sample_service.research_mode = research_mode

    reference = uuid.uuid4()
    mocker.patch('app.uuid.uuid4', return_value=reference)
    mocker.patch('app.aws_ses_client.send_email')
    mocker.patch('app.delivery.send_to_providers.send_email_response')

    send_to_providers.send_email_to_provider(
        notification
    )

    assert not app.aws_ses_client.send_email.called
    app.delivery.send_to_providers.send_email_response.assert_called_once_with(str(reference), 'john@smith.com')
    persisted_notification = Notification.query.filter_by(id=notification.id).one()
    assert persisted_notification.to == 'john@smith.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.status == 'sending'
    assert persisted_notification.sent_at <= datetime.utcnow()
    assert persisted_notification.created_at <= datetime.utcnow()
    assert persisted_notification.sent_by == 'ses'
    assert persisted_notification.reference == str(reference)
    assert persisted_notification.billable_units == 0


def test_send_email_to_provider_should_not_send_to_provider_when_status_is_not_created(
    sample_email_template,
    mocker
):
    notification = create_notification(template=sample_email_template, status='sending')
    mocker.patch('app.aws_ses_client.send_email')
    mocker.patch('app.delivery.send_to_providers.send_email_response')

    send_to_providers.send_sms_to_provider(
        notification
    )
    app.aws_ses_client.send_email.assert_not_called()
    app.delivery.send_to_providers.send_email_response.assert_not_called()


def test_send_email_should_use_service_reply_to_email(
        sample_service,
        sample_email_template,
        mocker):
    mocker.patch('app.aws_ses_client.send_email', return_value='reference')

    db_notification = create_notification(template=sample_email_template, reply_to_text='foo@bar.com')
    create_reply_to_email(service=sample_service, email_address='foo@bar.com')

    send_to_providers.send_email_to_provider(
        db_notification,
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        ANY,
        ANY,
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address='foo@bar.com'
    )


def test_get_html_email_renderer_should_return_for_normal_service(sample_service):
    options = send_to_providers.get_html_email_options(sample_service)
    assert options['govuk_banner'] is True
    assert 'brand_colour' not in options.keys()
    assert 'brand_logo' not in options.keys()
    assert 'brand_text' not in options.keys()
    assert 'brand_name' not in options.keys()


@pytest.mark.parametrize('branding_type, govuk_banner', [
    (BRANDING_ORG, False),
    (BRANDING_BOTH, True),
    (BRANDING_ORG_BANNER, False)
])
def test_get_html_email_renderer_with_branding_details(branding_type, govuk_banner, notify_db, sample_service):

    email_branding = EmailBranding(
        brand_type=branding_type,
        colour='#000000',
        logo='justice-league.png',
        name='Justice League',
        text='League of Justice',
    )
    sample_service.email_branding = email_branding
    notify_db.session.add_all([sample_service, email_branding])
    notify_db.session.commit()

    options = send_to_providers.get_html_email_options(sample_service)

    assert options['govuk_banner'] == govuk_banner
    assert options['brand_colour'] == '#000000'
    assert options['brand_text'] == 'League of Justice'
    assert options['brand_name'] == 'Justice League'

    if branding_type == BRANDING_ORG_BANNER:
        assert options['brand_banner'] is True
    else:
        assert options['brand_banner'] is False


def test_get_html_email_renderer_with_branding_details_and_render_govuk_banner_only(notify_db, sample_service):
    sample_service.email_branding = None
    notify_db.session.add_all([sample_service])
    notify_db.session.commit()

    options = send_to_providers.get_html_email_options(sample_service)

    assert options == {'govuk_banner': True, 'brand_banner': False}


def test_get_html_email_renderer_prepends_logo_path(notify_api):
    Service = namedtuple('Service', ['email_branding'])
    EmailBranding = namedtuple('EmailBranding', ['brand_type', 'colour', 'name', 'logo', 'text'])

    email_branding = EmailBranding(
        brand_type=BRANDING_ORG,
        colour='#000000',
        logo='justice-league.png',
        name='Justice League',
        text='League of Justice',
    )
    service = Service(
        email_branding=email_branding,
    )

    renderer = send_to_providers.get_html_email_options(service)

    assert renderer['brand_logo'] == 'http://static-logos.notify.tools/justice-league.png'


def test_get_html_email_renderer_handles_email_branding_without_logo(notify_api):
    Service = namedtuple('Service', ['email_branding'])
    EmailBranding = namedtuple('EmailBranding', ['brand_type', 'colour', 'name', 'logo', 'text'])

    email_branding = EmailBranding(
        brand_type=BRANDING_ORG_BANNER,
        colour='#000000',
        logo=None,
        name='Justice League',
        text='League of Justice',
    )
    service = Service(
        email_branding=email_branding,
    )

    renderer = send_to_providers.get_html_email_options(service)

    assert renderer['govuk_banner'] is False
    assert renderer['brand_banner'] is True
    assert renderer['brand_logo'] is None
    assert renderer['brand_text'] == 'League of Justice'
    assert renderer['brand_colour'] == '#000000'
    assert renderer['brand_name'] == 'Justice League'


@pytest.mark.parametrize('base_url, expected_url', [
    # don't change localhost to prevent errors when testing locally
    ('http://localhost:6012', 'http://static-logos.notify.tools/filename.png'),
    ('https://www.notifications.service.gov.uk', 'https://static-logos.notifications.service.gov.uk/filename.png'),
    ('https://notify.works', 'https://static-logos.notify.works/filename.png'),
    ('https://staging-notify.works', 'https://static-logos.staging-notify.works/filename.png'),
    ('https://www.notify.works', 'https://static-logos.notify.works/filename.png'),
    ('https://www.staging-notify.works', 'https://static-logos.staging-notify.works/filename.png'),
])
def test_get_logo_url_works_for_different_environments(base_url, expected_url):
    logo_file = 'filename.png'

    logo_url = send_to_providers.get_logo_url(base_url, logo_file)

    assert logo_url == expected_url


def test_should_not_update_notification_if_research_mode_on_exception(
        sample_service, sample_notification, mocker
):
    mocker.patch('app.delivery.send_to_providers.send_sms_response', side_effect=Exception())
    update_mock = mocker.patch('app.delivery.send_to_providers.update_notification_to_sending')
    sample_service.research_mode = True
    sample_notification.billable_units = 0

    with pytest.raises(Exception):
        send_to_providers.send_sms_to_provider(
            sample_notification
        )

    persisted_notification = notifications_dao.get_notification_by_id(sample_notification.id)
    assert persisted_notification.billable_units == 0
    assert update_mock.called


def __update_notification(notification_to_update, research_mode, expected_status):
    if research_mode or notification_to_update.key_type == KEY_TYPE_TEST:
        notification_to_update.status = expected_status


@pytest.mark.parametrize('research_mode,key_type, billable_units, expected_status', [
    (True, KEY_TYPE_NORMAL, 0, 'delivered'),
    (False, KEY_TYPE_NORMAL, 1, 'sending'),
    (False, KEY_TYPE_TEST, 0, 'sending'),
    (True, KEY_TYPE_TEST, 0, 'sending'),
    (True, KEY_TYPE_TEAM, 0, 'delivered'),
    (False, KEY_TYPE_TEAM, 1, 'sending')
])
def test_should_update_billable_units_and_status_according_to_research_mode_and_key_type(
    sample_template,
    mocker,
    research_mode,
    key_type,
    billable_units,
    expected_status
):
    notification = create_notification(template=sample_template, billable_units=0, status='created', key_type=key_type)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.delivery.send_to_providers.send_sms_response',
                 side_effect=__update_notification(notification, research_mode, expected_status))

    if research_mode:
        sample_template.service.research_mode = True

    send_to_providers.send_sms_to_provider(
        notification
    )
    assert notification.billable_units == billable_units
    assert notification.status == expected_status


def test_should_set_notification_billable_units_if_sending_to_provider_fails(
    sample_notification,
    mocker,
):
    mocker.patch('app.mmg_client.send_sms', side_effect=Exception())
    mocker.patch('app.delivery.send_to_providers.dao_reduce_sms_provider_priority')

    sample_notification.billable_units = 0
    assert sample_notification.sent_by is None

    with pytest.raises(Exception):
        send_to_providers.send_sms_to_provider(sample_notification)

    assert sample_notification.billable_units == 1


def test_should_send_sms_to_international_providers(
    sample_template,
    sample_user,
    mocker
):
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.firetext_client.send_sms')

    # set firetext to active
    get_provider_details_by_identifier('firetext').priority = 100
    get_provider_details_by_identifier('mmg').priority = 0

    notification_uk = create_notification(
        template=sample_template,
        to_field="+447234123999",
        personalisation={"name": "Jo"},
        status='created',
        international=False,
        reply_to_text=sample_template.service.get_default_sms_sender()
    )

    notification_international = create_notification(
        template=sample_template,
        to_field="+6011-17224412",
        personalisation={"name": "Jo"},
        status='created',
        international=True,
        reply_to_text=sample_template.service.get_default_sms_sender()
    )
    send_to_providers.send_sms_to_provider(
        notification_uk
    )

    firetext_client.send_sms.assert_called_once_with(
        to="447234123999",
        content=ANY,
        reference=str(notification_uk.id),
        sender=current_app.config['FROM_NUMBER']
    )

    send_to_providers.send_sms_to_provider(
        notification_international
    )

    mmg_client.send_sms.assert_called_once_with(
        to="601117224412",
        content=ANY,
        reference=str(notification_international.id),
        sender=current_app.config['FROM_NUMBER']
    )

    assert notification_uk.status == 'sending'
    assert notification_uk.sent_by == 'firetext'
    assert notification_international.status == 'sent'
    assert notification_international.sent_by == 'mmg'


@pytest.mark.parametrize('sms_sender, expected_sender, prefix_sms, expected_content', [
    ('foo', 'foo', False, 'bar'),
    ('foo', 'foo', True, 'Sample service: bar'),
    # if 40604 is actually in DB then treat that as if entered manually
    ('40604', '40604', False, 'bar'),
    # 'testing' is the FROM_NUMBER during unit tests
    ('testing', 'testing', True, 'Sample service: bar'),
    ('testing', 'testing', False, 'bar'),
])
def test_should_handle_sms_sender_and_prefix_message(
    mocker,
    sms_sender,
    prefix_sms,
    expected_sender,
    expected_content,
    notify_db_session
):
    mocker.patch('app.mmg_client.send_sms')
    service = create_service_with_defined_sms_sender(sms_sender_value=sms_sender, prefix_sms=prefix_sms)
    template = create_template(service, content='bar')
    notification = create_notification(template, reply_to_text=sms_sender)

    send_to_providers.send_sms_to_provider(notification)

    mmg_client.send_sms.assert_called_once_with(
        content=expected_content,
        sender=expected_sender,
        to=ANY,
        reference=ANY,
    )


def test_send_email_to_provider_uses_reply_to_from_notification(
        sample_email_template,
        mocker):
    mocker.patch('app.aws_ses_client.send_email', return_value='reference')

    db_notification = create_notification(template=sample_email_template, reply_to_text="test@test.com")

    send_to_providers.send_email_to_provider(
        db_notification,
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        ANY,
        ANY,
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address="test@test.com"
    )


def test_send_email_to_provider_should_format_reply_to_email_address(
        sample_email_template,
        mocker):
    mocker.patch('app.aws_ses_client.send_email', return_value='reference')

    db_notification = create_notification(template=sample_email_template, reply_to_text="test@test.com\t")

    send_to_providers.send_email_to_provider(
        db_notification,
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        ANY,
        ANY,
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address="test@test.com"
    )


def test_send_sms_to_provider_should_format_phone_number(sample_notification, mocker):
    sample_notification.to = '+44 (7123) 123-123'
    send_mock = mocker.patch('app.mmg_client.send_sms')

    send_to_providers.send_sms_to_provider(sample_notification)

    assert send_mock.call_args[1]['to'] == '447123123123'


def test_send_email_to_provider_should_format_email_address(sample_email_notification, mocker):
    sample_email_notification.to = 'test@example.com\t'
    send_mock = mocker.patch('app.aws_ses_client.send_email', return_value='reference')

    send_to_providers.send_email_to_provider(sample_email_notification)

    # to_addresses
    send_mock.assert_called_once_with(
        ANY,
        # to_addresses
        'test@example.com',
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address=ANY,
    )
