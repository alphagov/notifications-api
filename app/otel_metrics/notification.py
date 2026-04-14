from opentelemetry.metrics import get_meter

_meter = get_meter(__name__)

_international_sms = _meter.create_counter(
    "notification.sms.internationals",
    unit="{notification}",
    description=(
        "Number of international text messages sent; "
        "might be recorded multiple times per notification as it changes status from pending to delivered/failure"
    ),
)


def record_international_sms(amount: int, notification_status: str, sms_country_code: str) -> None:
    """
    Increments counter metric `notification.sms.internationals`, with the given attributes, by `amount`.
    """

    _international_sms.add(
        amount,
        {
            "notification.status": notification_status,
            "notification.sms.country_code": sms_country_code,
        },
    )
