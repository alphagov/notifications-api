import json

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

_deliver_duration = _meter.create_histogram(
    "notification.deliver.duration",
    unit="s",
    description=(
        "Elapsed time between notification creation datetime and delivery datetime reported by provider; "
        "might be recorded multiple times per notification as it changes status from pending to delivered/failure"
    ),
    # Buckets ranging from 1 second to 30 hours
    explicit_bucket_boundaries_advisory=[
        1,
        2,
        4,
        8,
        15,
        30,
        60,
        120,
        240,
        480,
        900,
        1800,
        3600,
        7200,
        14400,
        28800,
        54000,
        108000,
    ],
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


def record_deliver_duration(
    duration: float,
    key_type: str,
    notification_status: str,
    notification_type: str,
    provider_name: str,
    sms_international: bool | None = None,
) -> None:
    """
    Records a sample with the given `duration` and attributes for histogram metric `notification.deliver.duration`.
    """

    attrs = {
        "key.type": key_type,
        "notification.status": notification_status,
        "notification.type": notification_type,
        "provider.name": provider_name,
    }

    if sms_international is not None:
        # OTel semconv specifically dictates JSON encoding for booleans
        attrs["notification.sms.international"] = json.dumps(sms_international)

    _deliver_duration.record(duration, attrs)
