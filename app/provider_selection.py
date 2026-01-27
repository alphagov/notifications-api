from flask import current_app

from app.constants import EMAIL_TYPE, LETTER_TYPE, SMS_TYPE
from app.serialised_models import SerialisedProviders


def provider_option_enabled() -> bool:
    # Feature gate for explicit provider selection from API/CSV.
    return current_app.config.get("PROVIDER_OPTION_ENABLED", False)


def get_allowed_providers(notification_type: str, international: bool | None = False) -> set[str]:
    # Build allowed provider identifiers based on active providers and stub config.
    allowed: set[str] = set()

    if notification_type == SMS_TYPE:
        if international is None:
            allowed.update(
                p.identifier for p in SerialisedProviders.from_notification_type(notification_type, True) if p.active
            )
            allowed.update(
                p.identifier for p in SerialisedProviders.from_notification_type(notification_type, False) if p.active
            )
        else:
            allowed.update(
                p.identifier
                for p in SerialisedProviders.from_notification_type(notification_type, international)
                if p.active
            )
        if current_app.config.get("FIRETEXT_STUB_URL"):
            allowed.add("firetext-stub")
        if current_app.config.get("MMG_STUB_URL"):
            allowed.add("mmg-stub")

    elif notification_type == EMAIL_TYPE:
        allowed.update(
            p.identifier for p in SerialisedProviders.from_notification_type(notification_type, False) if p.active
        )
        if current_app.config.get("SES_STUB_URL"):
            allowed.add("ses-stub")

    elif notification_type == LETTER_TYPE:
        allowed.update(
            p.identifier for p in SerialisedProviders.from_notification_type(notification_type, False) if p.active
        )
        if current_app.config.get("LETTER_STUB_ENABLED"):
            allowed.add("dvla-stub")

    return allowed


def validate_provider_requested(
    provider_requested: str | None, notification_type: str, international: bool | None = False
) -> str | None:
    # Return an error message string when invalid; otherwise None.
    if provider_requested is None:
        return None

    if not provider_option_enabled():
        return "Provider option is not enabled"

    allowed = get_allowed_providers(notification_type, international=international)
    if provider_requested not in allowed:
        return f"Provider '{provider_requested}' is not valid for {notification_type} notifications"

    return None
