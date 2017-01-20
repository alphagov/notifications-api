from datetime import datetime

from sqlalchemy import asc

from app.dao.dao_utils import transactional
from app.provider_details.switch_providers import (
    provider_is_already_primary_or_inactive,
    update_provider_priorities
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
        notification_type=notification_type
    ).order_by(
        asc(ProviderDetails.priority)
    ).first()


@transactional
def dao_toggle_sms_provider():
    current_provider = get_current_provider('sms')
    alternate_provider = get_alternative_sms_provider(current_provider.identifier)
    dao_switch_sms_provider_to_provider_with_identifier(alternate_provider.identifier)


@transactional
def dao_switch_sms_provider_to_provider_with_identifier(identifier):
    current_provider = get_current_provider('sms')
    new_provider = get_provider_details_by_identifier(identifier)

    if provider_is_already_primary_or_inactive(current_provider, new_provider, identifier):
        return current_provider
    else:
        updated_providers = update_provider_priorities(current_provider, new_provider)
        for provider in updated_providers:
            db.session.add(provider)


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
