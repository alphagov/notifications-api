import json

from notifications_utils.semconv import TASK_DURATION_HISTOGRAM_BUCKETS, set_error_type
from opentelemetry.metrics import get_meter
from opentelemetry.util.types import AttributeValue

_meter = get_meter(__name__)

_international_sms = _meter.create_counter(
    "notification.sms.internationals",
    unit="{notification}",
    description=(
        "Number of international text messages sent; "
        "might be recorded multiple times per notification as it changes status from pending to delivered/failure"
    ),
)

_send_duration = _meter.create_histogram(
    "notification.send.duration",
    unit="s",
    description="Elapsed time between notification creation and sending to provider",
    explicit_bucket_boundaries_advisory=TASK_DURATION_HISTOGRAM_BUCKETS,
)

# Buckets ranging from 1 second to 30 hours
DELIVER_DURATION_HISTOGRAM_BUCKETS = [
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
]

_callback_duration = _meter.create_histogram(
    "notification.callback.duration",
    unit="s",
    description=(
        "Elapsed time between notification creation datetime and receipt of a callback from the provider; "
        "might be recorded multiple times per notification as it changes status from pending to delivered/failure"
    ),
    explicit_bucket_boundaries_advisory=DELIVER_DURATION_HISTOGRAM_BUCKETS,
)

_deliver_duration = _meter.create_histogram(
    "notification.deliver.duration",
    unit="s",
    description=(
        "Elapsed time between notification creation datetime and delivery datetime reported by provider; "
        "might be recorded multiple times per notification as it changes status from pending to delivered/failure"
    ),
    explicit_bucket_boundaries_advisory=DELIVER_DURATION_HISTOGRAM_BUCKETS,
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


def record_send_duration(duration: float, key_type: str, notification_type: str, provider_name: str) -> None:
    """
    Records a sample with the given `duration` and attributes for histogram metric `notification.send.duration`, and
    captures the fully-qualified name of the current exception (if any) as attribute `error.type`.
    """

    attributes: dict[str, AttributeValue] = {
        "key.type": key_type,
        "notification.type": notification_type,
        "provider.name": provider_name,
    }

    set_error_type(attributes)

    _send_duration.record(
        duration,
        attributes,
    )


def record_deliver_duration(
    callback_duration: float | None,
    deliver_duration: float | None,
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

    if callback_duration is not None:
        _callback_duration.record(callback_duration, attrs)
    if deliver_duration is not None:
        _deliver_duration.record(deliver_duration, attrs)
