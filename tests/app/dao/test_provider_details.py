from app.models import ProviderDetails
from app import clients


def test_should_error_if_any_provider_in_database_not_in_code(notify_db, notify_db_session, notify_api):
    providers = ProviderDetails.query.all()

    for provider in providers:
        if provider.notification_type == 'sms':
            assert clients.sms_client(provider.identifier)
        if provider.notification_type == 'email':
            assert clients.email_client(provider.identifier)


def test_should_not_error_if_any_provider_in_code_not_in_database(notify_db, notify_db_session, notify_api):
    providers = ProviderDetails.query.all()

    ProviderDetails.query.filter_by(identifier='mmg').delete()

    for provider in providers:
        if provider.notification_type == 'sms':
            assert clients.sms_client(provider.identifier)
        if provider.notification_type == 'email':
            assert clients.email_client(provider.identifier)
