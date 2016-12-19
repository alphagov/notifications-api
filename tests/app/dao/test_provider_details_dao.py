from app.models import ProviderDetails
from app import clients
from app.dao.provider_details_dao import (
    get_provider_details,
    get_provider_details_by_notification_type
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
