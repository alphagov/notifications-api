from datetime import datetime

from sqlalchemy import asc, desc

from app.dao.dao_utils import transactional
from app.provider_details.switch_providers import (
    provider_is_inactive,
    provider_is_primary,
    switch_providers
)
from app.models import ProviderDetails, ProviderDetailsHistory
from app import db


def get_provider_details():
    return ProviderDetails.query.order_by(asc(ProviderDetails.priority), asc(ProviderDetails.notification_type)).all()


def get_provider_details_by_id(provider_details_id):
    return ProviderDetails.query.get(provider_details_id)


def get_provider_details_by_identifier(identifier):
    return ProviderDetails.query.filter_by(identifier=identifier).one()


def get_alternative_sms_provider(identifier):
    alternate_provider = None
    if identifier == 'firetext':
        alternate_provider = 'mmg'
    elif identifier == 'mmg':
        alternate_provider = 'firetext'

    return ProviderDetails.query.filter_by(identifier=alternate_provider).one()


def get_current_provider(notification_type):
    return ProviderDetails.query.filter_by(
        notification_type=notification_type,
        active=True
    ).order_by(
        asc(ProviderDetails.priority)
    ).first()


def dao_get_provider_versions(provider_id):
    return ProviderDetailsHistory.query.filter_by(
        id=provider_id
    ).order_by(
        desc(ProviderDetailsHistory.version)
    ).all()


@transactional
def dao_toggle_sms_provider(identifier):
    alternate_provider = get_alternative_sms_provider(identifier)
    dao_switch_sms_provider_to_provider_with_identifier(alternate_provider.identifier)


@transactional
def dao_switch_sms_provider_to_provider_with_identifier(identifier):
    new_provider = get_provider_details_by_identifier(identifier)
    if provider_is_inactive(new_provider):
        return

    # Check first to see if there is another provider with the same priority
    # as this needs to be updated differently
    conflicting_provider = dao_get_sms_provider_with_equal_priority(new_provider.identifier, new_provider.priority)
    providers_to_update = []

    if conflicting_provider:
        providers_to_update = switch_providers(conflicting_provider, new_provider)
    else:
        current_provider = get_current_provider('sms')
        if not provider_is_primary(current_provider, new_provider, identifier):
            providers_to_update = switch_providers(current_provider, new_provider)

        for provider in providers_to_update:
            dao_update_provider_details(provider)


def get_provider_details_by_notification_type(notification_type):
    return ProviderDetails.query.filter_by(
        notification_type=notification_type
    ).order_by(asc(ProviderDetails.priority)).all()


@transactional
def dao_update_provider_details(provider_details):
    provider_details.version += 1
    provider_details.updated_at = datetime.utcnow()
    history = ProviderDetailsHistory.from_original(provider_details)
    db.session.add(provider_details)
    db.session.add(history)


def dao_get_sms_provider_with_equal_priority(identifier, priority):
    provider = db.session.query(ProviderDetails).filter(
        ProviderDetails.identifier != identifier,
        ProviderDetails.notification_type == 'sms',
        ProviderDetails.priority == priority,
        ProviderDetails.active
    ).order_by(
        asc(ProviderDetails.priority)
    ).first()

    return provider
