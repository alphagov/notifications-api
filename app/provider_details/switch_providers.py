from flask import current_app

from app.dao.users_dao import get_user_by_id


def provider_is_inactive(new_provider):
    if not new_provider.active:
        current_app.logger.warning('Cancelling switch to {} as they are inactive'.format(
            new_provider.identifier,
        ))
        return True


def provider_is_primary(current_provider, new_provider, identifier):
    if current_provider.identifier == identifier:
        current_app.logger.warning('Provider {} is already activated'.format(current_provider.display_name))
        return True

    return False


def switch_providers(current_provider, new_provider):
    # Automatic update so set as notify user
    notify_user = get_user_by_id(current_app.config['NOTIFY_USER_ID'])
    current_provider.created_by_id = new_provider.created_by_id = notify_user.id

    # Swap priority to change primary provider
    if new_provider.priority > current_provider.priority:
        new_provider.priority, current_provider.priority = current_provider.priority, new_provider.priority

    # Increase other provider priority if equal
    elif new_provider.priority == current_provider.priority:
        current_provider.priority += 10

    _print_provider_switch_logs(current_provider, new_provider)
    return current_provider, new_provider


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
