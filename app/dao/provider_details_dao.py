from datetime import datetime

from flask import current_app
from sqlalchemy import asc

from app.dao.dao_utils import transactional
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
    # Do nothing if the provider is already primary or set as inactive
    current_provider = get_current_provider('sms')
    if current_provider.identifier == identifier:
        current_app.logger.warning('Provider {} is already activated'.format(current_provider.display_name))
        return current_provider

    new_provider = get_provider_details_by_identifier(identifier)
    if not new_provider.active:
        current_app.logger.warning('Cancelling switch from {} to {} as {} is inactive'.format(
            current_provider.identifier,
            new_provider.identifier,
            new_provider.identifier
        ))
        return current_provider

    # Swap priority to change primary provider
    if new_provider.priority > current_provider.priority:
        new_provider.priority, current_provider.priority = current_provider.priority, new_provider.priority
        _print_provider_switch_logs(current_provider, new_provider)
        db.session.add_all([current_provider, new_provider])

    # Incease other provider priority if equal
    elif new_provider.priority == current_provider.priority:
        current_provider.priority += 10
        _print_provider_switch_logs(current_provider, new_provider)
        db.session.add(current_provider)


def _print_provider_switch_logs(current_provider, new_provider):
    current_app.logger.warning('Switching provider from {} to {}'.format(
        current_provider.identifier,
        new_provider.identifier
    ))

    current_app.logger.warning('Provider {} now updated with priority of {}'.format(
        current_provider.identifier,
        current_provider.priority
    ))

    current_app.logger.warning('Provider {} now updated with priority of {}'.format(
        new_provider.identifier,
        new_provider.priority
    ))


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
