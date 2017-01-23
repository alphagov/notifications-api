from flask import current_app


def provider_is_already_primary_or_inactive(current_provider, new_provider, identifier):
    if current_provider.identifier == identifier:
        current_app.logger.warning('Provider {} is already activated'.format(current_provider.display_name))
        return True

    elif not new_provider.active:
        current_app.logger.warning('Cancelling switch from {} to {} as {} is inactive'.format(
            current_provider.identifier,
            new_provider.identifier,
            new_provider.identifier
        ))
        return True

    return False


def update_provider_priorities(current_provider, new_provider):
    # Swap priority to change primary provider
    if new_provider.priority > current_provider.priority:
        new_provider.priority, current_provider.priority = current_provider.priority, new_provider.priority

    # Incease other provider priority if equal
    elif new_provider.priority == current_provider.priority:
        current_provider.priority += 10

    _print_provider_switch_logs(current_provider, new_provider)


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
