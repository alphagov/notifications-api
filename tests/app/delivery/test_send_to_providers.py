import uuid
from datetime import datetime

import pytest
from mock import ANY

import app
from app import mmg_client
from app.dao import (provider_details_dao, notifications_dao, provider_statistics_dao)
from app.dao.provider_statistics_dao import get_provider_statistics
from app.delivery import send_to_providers
from app.models import Notification, KEY_TYPE_NORMAL, KEY_TYPE_TEST, BRANDING_ORG, BRANDING_BOTH, Organisation
from tests.app.conftest import sample_notification

from notifications_utils.recipients import validate_phone_number, format_phone_number


def test_should_return_highest_priority_active_provider(notify_db, notify_db_session):
    providers = provider_details_dao.get_provider_details_by_notification_type('sms')

    first = providers[0]
    second = providers[1]

    assert send_to_providers.provider_to_use('sms', '1234').name == first.identifier

    first.priority = 20
    second.priority = 10

    provider_details_dao.dao_update_provider_details(first)
    provider_details_dao.dao_update_provider_details(second)

    assert send_to_providers.provider_to_use('sms', '1234').name == second.identifier

    first.priority = 10
    first.active = False
    second.priority = 20

    provider_details_dao.dao_update_provider_details(first)
    provider_details_dao.dao_update_provider_details(second)

    assert send_to_providers.provider_to_use('sms', '1234').name == second.identifier

    first.active = True
    provider_details_dao.dao_update_provider_details(first)

    assert send_to_providers.provider_to_use('sms', '1234').name == first.identifier


def test_should_send_personalised_template_to_correct_sms_provider_and_persist(
    notify_db,
    notify_db_session,
    sample_template_with_placeholders,
    mocker
):
    db_notification = sample_notification(notify_db, notify_db_session, template=sample_template_with_placeholders,
                                          to_field="+447234123123", personalisation={"name": "Jo"},
                                          status='created')

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")

    send_to_providers.send_sms_to_provider(
        db_notification.id
    )

    mmg_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: Hello Jo\nYour thing is due soon",
        reference=str(db_notification.id),
        sender=None
    )
    notification = Notification.query.filter_by(id=db_notification.id).one()

    assert notification.status == 'sending'
    assert notification.sent_at <= datetime.utcnow()
    assert notification.sent_by == 'mmg'
    assert notification.billable_units == 1
    assert notification.personalisation == {"name": "Jo"}


def test_should_send_personalised_template_to_correct_email_provider_and_persist(
    notify_db,
    notify_db_session,
    sample_email_template_with_placeholders,
    mocker
):
    db_notification = sample_notification(
        notify_db=notify_db, notify_db_session=notify_db_session,
        template=sample_email_template_with_placeholders,
        to_field="jo.smith@example.com",
        personalisation={'name': 'Jo'}
    )

    mocker.patch('app.aws_ses_client.send_email', return_value='reference')
    mocker.patch('app.aws_ses_client.get_name', return_value="ses")

    send_to_providers.send_email_to_provider(
        db_notification.id
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        '"Sample service" <sample.service@test.notify.com>',
        'jo.smith@example.com',
        'Jo',
        body='Hello Jo\nThis is an email from GOV.\u200bUK',
        html_body=ANY,
        reply_to_address=None
    )
    assert '<!DOCTYPE html' in app.aws_ses_client.send_email.call_args[1]['html_body']

    notification = Notification.query.filter_by(id=db_notification.id).one()

    assert notification.status == 'sending'
    assert notification.sent_at <= datetime.utcnow()
    assert notification.sent_by == 'ses'
    assert notification.personalisation == {"name": "Jo"}


def test_send_sms_should_use_template_version_from_notification_not_latest(
        notify_db,
        notify_db_session,
        sample_template,
        mocker):
    db_notification = sample_notification(notify_db, notify_db_session,
                                          template=sample_template, to_field='+447234123123',
                                          status='created')

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    version_on_notification = sample_template.version

    # Change the template
    from app.dao.templates_dao import dao_update_template, dao_get_template_by_id
    sample_template.content = sample_template.content + " another version of the template"
    dao_update_template(sample_template)
    t = dao_get_template_by_id(sample_template.id)
    assert t.version > version_on_notification

    send_to_providers.send_sms_to_provider(
        db_notification.id
    )

    mmg_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: This is a template:\nwith a newline",
        reference=str(db_notification.id),
        sender=None
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
def test_should_call_send_sms_response_task_if_research_mode(notify_db, sample_service, sample_notification, mocker,
                                                             research_mode, key_type):
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    if research_mode:
        sample_service.research_mode = True
        notify_db.session.add(sample_service)
        notify_db.session.commit()

    sample_notification.key_type = key_type

    send_to_providers.send_sms_to_provider(
        sample_notification.id
    )
    assert not mmg_client.send_sms.called
    send_to_providers.send_sms_response.apply_async.assert_called_once_with(
        ('mmg', str(sample_notification.id), sample_notification.to), queue='research-mode'
    )

    persisted_notification = notifications_dao.get_notification_by_id(sample_notification.id)
    assert persisted_notification.to == sample_notification.to
    assert persisted_notification.template_id == sample_notification.template_id
    assert persisted_notification.status == 'sending'
    assert persisted_notification.sent_at <= datetime.utcnow()
    assert persisted_notification.sent_by == 'mmg'
    assert not persisted_notification.personalisation


@pytest.mark.parametrize('research_mode,key_type', [
    (True, KEY_TYPE_NORMAL),
    (False, KEY_TYPE_TEST)
])
def test_should_set_billable_units_to_zero_in_research_mode_or_test_key(
        notify_db, sample_service, sample_notification, mocker, research_mode, key_type):
    provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert len(provider_stats) == 0

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')
    if research_mode:
        sample_service.research_mode = True
        notify_db.session.add(sample_service)
        notify_db.session.commit()
    sample_notification.key_type = key_type

    send_to_providers.send_sms_to_provider(
        sample_notification.id
    )

    assert notifications_dao.get_notification_by_id(sample_notification.id).billable_units == 0


def test_should_not_send_to_provider_when_status_is_not_created(notify_db, notify_db_session,
                                                                sample_service,
                                                                mocker):
    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       service=sample_service,
                                       status='sending')
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    send_to_providers.send_sms_to_provider(
        notification.id
    )

    app.mmg_client.send_sms.assert_not_called()
    app.celery.research_mode_tasks.send_sms_response.apply_async.assert_not_called()


def test_should_send_sms_sender_from_service_if_present(
        notify_db,
        notify_db_session,
        sample_service,
        sample_template,
        mocker):
    db_notification = sample_notification(notify_db, notify_db_session, template=sample_template,
                                          to_field="+447234123123",
                                          status='created')

    sample_service.sms_sender = 'elevenchars'
    notify_db.session.add(sample_service)
    notify_db.session.commit()

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")

    send_to_providers.send_sms_to_provider(
        db_notification.id
    )

    mmg_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="This is a template:\nwith a newline",
        reference=str(db_notification.id),
        sender=sample_service.sms_sender
    )


@pytest.mark.parametrize('research_mode,key_type', [
    (True, KEY_TYPE_NORMAL),
    (False, KEY_TYPE_TEST)
])
def test_send_email_to_provider_should_call_research_mode_task_response_task_if_research_mode(
        notify_db,
        notify_db_session,
        sample_service,
        sample_email_template,
        ses_provider,
        mocker,
        research_mode,
        key_type):
    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       template=sample_email_template,
                                       to_field="john@smith.com",
                                       key_type=key_type
                                       )

    reference = uuid.uuid4()
    mocker.patch('app.uuid.uuid4', return_value=reference)
    mocker.patch('app.aws_ses_client.send_email')
    mocker.patch('app.aws_ses_client.get_name', return_value="ses")
    mocker.patch('app.celery.research_mode_tasks.send_email_response.apply_async')

    if research_mode:
        sample_service.research_mode = True
        notify_db.session.add(sample_service)
        notify_db.session.commit()
    assert not get_provider_statistics(
        sample_email_template.service,
        providers=[ses_provider.identifier]).first()
    send_to_providers.send_email_to_provider(
        notification.id
    )
    assert not app.aws_ses_client.send_email.called
    send_to_providers.send_email_response.apply_async.assert_called_once_with(
        ('ses', str(reference), 'john@smith.com'), queue="research-mode"
    )
    assert not get_provider_statistics(
        sample_email_template.service,
        providers=[ses_provider.identifier]).first()
    persisted_notification = Notification.query.filter_by(id=notification.id).one()

    assert persisted_notification.to == 'john@smith.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.status == 'sending'
    assert persisted_notification.sent_at <= datetime.utcnow()
    assert persisted_notification.created_at <= datetime.utcnow()
    assert persisted_notification.sent_by == 'ses'
    assert persisted_notification.reference == str(reference)


def test_send_email_to_provider_should_not_send_to_provider_when_status_is_not_created(notify_db, notify_db_session,
                                                                                       sample_service,
                                                                                       sample_email_template,
                                                                                       mocker):
    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       template=sample_email_template,
                                       service=sample_service,
                                       status='sending')
    mocker.patch('app.aws_ses_client.send_email')
    mocker.patch('app.aws_ses_client.get_name', return_value="ses")
    mocker.patch('app.celery.research_mode_tasks.send_email_response.apply_async')

    send_to_providers.send_sms_to_provider(
        notification.id
    )

    app.aws_ses_client.send_email.assert_not_called()
    app.celery.research_mode_tasks.send_email_response.apply_async.assert_not_called()


def test_send_email_should_use_service_reply_to_email(
        notify_db, notify_db_session,
        sample_service,
        sample_email_template,
        mocker):
    mocker.patch('app.aws_ses_client.send_email', return_value='reference')
    mocker.patch('app.aws_ses_client.get_name', return_value="ses")

    db_notification = sample_notification(notify_db, notify_db_session, template=sample_email_template)
    sample_service.reply_to_email_address = 'foo@bar.com'

    send_to_providers.send_email_to_provider(
        db_notification.id,
    )

    app.aws_ses_client.send_email.assert_called_once_with(
        ANY,
        ANY,
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address=sample_service.reply_to_email_address
    )


def test_get_html_email_renderer_should_return_for_normal_service(sample_service):
    renderer = send_to_providers.get_html_email_renderer(sample_service)
    assert renderer.govuk_banner
    assert renderer.brand_colour is None
    assert renderer.brand_logo is None
    assert renderer.brand_name is None


@pytest.mark.parametrize('branding_type, govuk_banner', [
    (BRANDING_ORG, False),
    (BRANDING_BOTH, True)
])
def test_get_html_email_renderer_with_branding_details(branding_type, govuk_banner, notify_db, sample_service):
    sample_service.branding = branding_type
    org = Organisation(colour='#000000', logo='justice-league.png', name='Justice League')
    sample_service.organisation = org
    notify_db.session.add_all([sample_service, org])
    notify_db.session.commit()

    renderer = send_to_providers.get_html_email_renderer(sample_service)

    assert renderer.govuk_banner == govuk_banner
    assert renderer.brand_colour == '000000'
    assert renderer.brand_name == 'Justice League'


def test_get_html_email_renderer_prepends_logo_path(notify_db, sample_service):
    sample_service.branding = BRANDING_ORG
    org = Organisation(colour='#000000', logo='justice-league.png', name='Justice League')
    sample_service.organisation = org
    notify_db.session.add_all([sample_service, org])
    notify_db.session.commit()

    renderer = send_to_providers.get_html_email_renderer(sample_service)

    assert renderer.brand_logo == 'http://localhost:6012/static/images/email-template/crests/justice-league.png'


def test_should_not_set_billable_units_if_research_mode(notify_db, sample_service, sample_notification, mocker):
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    sample_service.research_mode = True
    notify_db.session.add(sample_service)
    notify_db.session.commit()

    send_to_providers.send_sms_to_provider(
        sample_notification.id
    )

    persisted_notification = notifications_dao.get_notification_by_id(sample_notification.id)
    assert persisted_notification.billable_units == 0
