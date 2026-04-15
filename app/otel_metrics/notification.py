from opentelemetry.metrics import get_meter

_meter = get_meter(__name__)

_international_sms = _meter.create_counter(
    "notification.sms.internationals",
    unit="{notification}",
    description="Number of international text messages sent",
)

_deliver_duration = _meter.create_histogram(
    "notification.deliver.duration",
    unit="s",
    description="Elapsed time between notification creation datetime and delivery datetime reported by provider",
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
    duration: float, key_type: str, notification_status: str, notification_type: str, provider_name: str
) -> None:
    """
    Records a sample with the given `duration` and attributes for histogram metric `notification.deliver.duration`.
    """

    _deliver_duration.record(
        duration,
        {
            "key.type": key_type,
            "notification.status": notification_status,
            "notification.type": notification_type,
            "provider.name": provider_name,
        },
    )
