import pytest

from datetime import datetime, timedelta

from freezegun import freeze_time

from app.models import ProviderDetails, ProviderDetailsHistory
from app import clients
from app.dao.provider_details_dao import (
    dao_switch_sms_provider,
    get_current_provider,
    get_alternative_sms_provider,
    get_provider_details,
    get_provider_details_by_id,
    get_provider_details_by_notification_type,
    dao_update_provider_details
)
from tests.app.conftest import (
    sample_notification as create_sample_notification,
    set_primary_sms_provider
)


def test_can_get_all_providers(restore_provider_details):
    assert len(get_provider_details()) == 4


def test_can_get_sms_providers(restore_provider_details):
    sms_providers = get_provider_details_by_notification_type('sms')
    assert len(sms_providers) == 3
    assert all('sms' == prov.notification_type for prov in sms_providers)


def test_can_get_sms_providers_in_order(restore_provider_details):
    providers = get_provider_details_by_notification_type('sms')

    assert providers[0].identifier == "mmg"
    assert providers[1].identifier == "firetext"
    assert providers[2].identifier == "loadtesting"


def test_can_get_email_providers_in_order(restore_provider_details):
    providers = get_provider_details_by_notification_type('email')

    assert providers[0].identifier == "ses"


def test_can_get_email_providers(restore_provider_details):
    assert len(get_provider_details_by_notification_type('email')) == 1
    types = [provider.notification_type for provider in get_provider_details_by_notification_type('email')]
    assert all('email' == notification_type for notification_type in types)


def test_should_not_error_if_any_provider_in_code_not_in_database(restore_provider_details):
    providers = ProviderDetails.query.all()

    ProviderDetails.query.filter_by(identifier='mmg').delete()

    assert clients.get_sms_client('mmg')


@freeze_time('2000-01-01T00:00:00')
def test_update_adds_history(restore_provider_details):
    ses = ProviderDetails.query.filter(ProviderDetails.identifier == 'ses').one()
    ses_history = ProviderDetailsHistory.query.filter(ProviderDetailsHistory.id == ses.id).one()

    assert ses.version == 1
    assert ses_history.version == 1
    assert ses.updated_at is None

    ses.active = False

    dao_update_provider_details(ses)

    assert not ses.active
    assert ses.updated_at == datetime(2000, 1, 1, 0, 0, 0)

    ses_history = ProviderDetailsHistory.query.filter(
        ProviderDetailsHistory.id == ses.id
    ).order_by(
        ProviderDetailsHistory.version
    ).all()

    assert ses_history[0].active
    assert ses_history[0].version == 1
    assert ses_history[0].updated_at is None

    assert not ses_history[1].active
    assert ses_history[1].version == 2
    assert ses_history[1].updated_at == datetime(2000, 1, 1, 0, 0, 0)


def test_get_current_provider_sms_returns_correct_provider(restore_provider_details):
    set_primary_sms_provider('mmg')

    provider = get_current_provider('sms')

    assert provider.identifier == 'mmg'


@pytest.mark.parametrize('provider_identifier', ['firetext', 'mmg'])
def test_get_alternative_sms_provider_returns_expected_provider(notify_db, provider_identifier):
    provider = get_alternative_sms_provider(provider_identifier)
    assert provider.identifier != provider


def test_switch_sms_provider_switches_on_slow_delivery(
    notify_db,
    notify_db_session,
    current_sms_provider,
    restore_provider_details
):
    # A notification that has been in sending for 7 mins
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        created_at=datetime.utcnow() - timedelta(minutes=10),
        sent_at=datetime.utcnow() - timedelta(minutes=3),
        status='sending',
        sent_by=current_sms_provider.identifier
    )

    dao_switch_sms_provider(notification.sent_by)

    old_provider = get_provider_details_by_id(current_sms_provider.id)
    new_provider = get_current_provider('sms')

    assert current_sms_provider.identifier != new_provider.identifier
    assert new_provider.priority < old_provider.priority


def test_switch_sms_provider_already_activated_does_not_switch(
    notify_db,
    notify_db_session,
    current_sms_provider,
    restore_provider_details,
    mocker
):
    alternate_sms_provider = get_alternative_sms_provider(current_sms_provider.identifier)
    # A notification that has been in sending for 7 mins
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        created_at=datetime.utcnow() - timedelta(minutes=10),
        sent_at=datetime.utcnow() - timedelta(minutes=3),
        status='sending',
        sent_by=alternate_sms_provider.identifier  # Must be alternate sms provider (not activated)
    )

    dao_switch_sms_provider(notification.sent_by)

    new_provider = get_current_provider('sms')

    assert current_sms_provider.id == new_provider.id
    assert current_sms_provider.identifier == new_provider.identifier
