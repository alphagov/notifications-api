from datetime import datetime

from sqlalchemy import asc
from app.dao.dao_utils import transactional
from app.models import ProviderDetails, ProviderDetailsHistory
from app import db
from flask import current_app


def get_provider_details():
    return ProviderDetails.query.order_by(asc(ProviderDetails.priority), asc(ProviderDetails.notification_type)).all()


def get_provider_details_by_id(provider_details_id):
    return ProviderDetails.query.get(provider_details_id)


def get_provider_details_by_identifier(identifier):
    return ProviderDetails.query.filter_by(identifier=identifier).one()


def get_alternative_sms_provider(identifier):
    sms_providers = set(['firetext', 'mmg'])
    selected_provider = None
    try:
        selected_provider = sms_providers.difference([identifier]).pop()
    except KeyError:
        current_app.logger.error('Could not get an alternative sms provider from list {} given {}').format(
            sms_providers,
            identifier
        )
    else:
        return ProviderDetails.query.filter_by(
            identifier=selected_provider
        ).one()


def get_provider_details_by_notification_type(notification_type):
    return ProviderDetails.query.filter_by(
        notification_type=notification_type
    ).order_by(asc(ProviderDetails.priority)).all()


def get_current_provider(notification_type):
    return ProviderDetails.query.filter_by(
        notification_type=notification_type
    ).order_by(
        asc(ProviderDetails.priority)
    ).first()


@transactional
def dao_update_provider_details(provider_details):
    provider_details.version += 1
    provider_details.updated_at = datetime.utcnow()
    history = ProviderDetailsHistory.from_original(provider_details)
    db.session.add(provider_details)
    db.session.add(history)


@transactional
def dao_switch_sms_provider(identifier):
    current_provider = get_current_provider('sms')
    new_provider = get_alternative_sms_provider(identifier)

    if not new_provider.active:
        current_app.logger.info('Cancelling switch from {} to {} as {} is inactive'.format(
            current_provider.identifier,
            new_provider.identifier,
            new_provider.identifier
        ))

        return current_provider

    if current_provider.identifier == new_provider.identifier:
        current_app.logger.info('Alternative provider {} is already activated'.format(new_provider.identifier))
        return current_provider

    else:

        # Swap priority to change primary provider
        if new_provider.priority > current_provider.priority:
            new_provider.priority, current_provider.priority = current_provider.priority, new_provider.priority
            _print_provider_switch_logs(current_provider, new_provider)
            db.session.add_all([current_provider, new_provider])

        # Reduce other provider priority if equal
        elif new_provider.priority == current_provider.priority:
            current_provider.priority += 10
            _print_provider_switch_logs(current_provider, new_provider)
            db.session.add(current_provider)


def _print_provider_switch_logs(current_provider, new_provider):
    current_app.logger.info('Switching provider from {} to {}'.format(
        current_provider.identifier,
        new_provider.identifier
    ))

    current_app.logger.info('Provider {} now updated with priority of {}'.format(
        current_provider.identifier,
        current_provider.priority
    ))

    current_app.logger.info('Provider {} now updated with priority of {}'.format(
        new_provider.identifier,
        new_provider.priority
    ))
