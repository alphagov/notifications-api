from app.models import ProviderDetails
from app import clients
from app.dao.provider_details_dao import (
    get_provider_details,
    get_provider_details_by_notification_type
)


def test_can_get_all_providers(notify_db, notify_db_session):
    assert len(get_provider_details()) == 3


def test_can_get_sms_providers(notify_db, notify_db_session):
    assert len(get_provider_details_by_notification_type('sms')) == 2
    types = [provider.notification_type for provider in get_provider_details_by_notification_type('sms')]
    assert all('sms' == notification_type for notification_type in types)


def test_can_get_sms_providers_in_order(notify_db, notify_db_session):
    providers = get_provider_details_by_notification_type('sms')

    assert providers[0].identifier == "mmg"
    assert providers[1].identifier == "firetext"


def test_can_get_email_providers_in_order(notify_db, notify_db_session):
    providers = get_provider_details_by_notification_type('email')

    assert providers[0].identifier == "ses"


def test_can_get_email_providers(notify_db, notify_db_session):
    assert len(get_provider_details_by_notification_type('email')) == 1
    types = [provider.notification_type for provider in get_provider_details_by_notification_type('email')]
    assert all('email' == notification_type for notification_type in types)


def test_should_error_if_any_provider_in_database_not_in_code(notify_db, notify_db_session, notify_api):
    providers = ProviderDetails.query.all()

    for provider in providers:
        if provider.notification_type == 'sms':
            assert clients.get_sms_client(provider.identifier)
        if provider.notification_type == 'email':
            assert clients.get_email_client(provider.identifier)


def test_should_not_error_if_any_provider_in_code_not_in_database(notify_db, notify_db_session, notify_api):
    providers = ProviderDetails.query.all()

    ProviderDetails.query.filter_by(identifier='mmg').delete()

    for provider in providers:
        if provider.notification_type == 'sms':
            assert clients.get_sms_client(provider.identifier)
        if provider.notification_type == 'email':
            assert clients.get_email_client(provider.identifier)
