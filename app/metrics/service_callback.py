from notifications_utils.semconv import set_error_type
from opentelemetry.metrics import get_meter
from opentelemetry.util.types import AttributeValue

_meter = get_meter(__name__)

# Buckets ranging from 50 milliseconds to 10 minutes
SERVICE_CALLBACK_FORWARD_DURATION_HISTOGRAM_BUCKETS = [
    0.05,
    0.1,
    0.2,
    0.5,
    1,
    2,
    5,
    10,
    30,
    60,
    120,
    300,
    600,
]

_service_callback_forward_duration = _meter.create_histogram(
    "service_callback.forward.duration",
    unit="s",
    description="Elapsed time between provider receipt and start of service callback attempt",
    explicit_bucket_boundaries_advisory=SERVICE_CALLBACK_FORWARD_DURATION_HISTOGRAM_BUCKETS,
)


def record_service_callback_forward_duration(
    duration: float,
    callback_type: str,
    attempt: int,
    notification_type: str | None = None,
):
    attrs: dict[str, AttributeValue] = {
        "callback.type": callback_type,
        "callback.attempt": attempt,
    }

    if notification_type is not None:
        attrs["notification.type"] = notification_type

    set_error_type(attrs)

    _service_callback_forward_duration.record(duration, attrs)
