import datetime
import functools
from collections.abc import Callable
from time import monotonic

from notifications_utils.semconv import HTTP_DURATION_HISTOGRAM_BUCKETS, set_error_type
from opentelemetry.metrics import get_meter
from opentelemetry.util.types import AttributeValue

_meter = get_meter(__name__)

_request_duration = _meter.create_histogram(
    "provider.request.duration",
    unit="s",
    description="Duration of (HTTP) requests to providers",
    explicit_bucket_boundaries_advisory=HTTP_DURATION_HISTOGRAM_BUCKETS,
)

_sms_legacy_not_delivered_within = _meter.create_gauge(
    "provider.sms.legacy.not_delivered_within",
    unit="1",
    description="Proportion of SMS messages sent in the last time_window.evaluation seconds "
    "that were not delivered within time_window.delivery seconds. BEWARE this is a flawed metric "
    "as it includes notifications sent too recently to be able to determine this for sensibly, "
    "however this is the measure currently used by the SMS provider balancer for better or "
    "worse.",
)

_priority = _meter.create_gauge(
    "provider.priority",
    unit="1",
    description="Observed priority value of a Provider",
)

_updated_at = _meter.create_gauge(
    "provider.updated_at",
    unit="s",
    description="Unix epoch timestamp of Provider's last update",
)

_info = _meter.create_gauge(
    "provider.info",
    unit="1",
    description="Observed metadata values of a Provider",
)


def record_request_duration[**P, T](
    notification_type: str, provider_name: str
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Returns a decorator that instruments the duration of the decorated function as histogram `provider.request.duration`
    with the given attributes, and captures the fully-qualified name of any exception the function raises as attribute
    `error.type`.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start_time = monotonic()
            try:
                return func(*args, **kwargs)
            finally:
                attributes: dict[str, AttributeValue] = {
                    "notification.type": notification_type,
                    "provider.name": provider_name,
                }
                set_error_type(attributes)
                _request_duration.record(monotonic() - start_time, attributes)

        return wrapper

    return decorator


def record_sms_legacy_not_delivered_within(
    ratio: float, provider_name: str, delivery_window: int, evaluation_window: int
) -> None:
    attributes: dict[str, AttributeValue] = {
        "provider.name": provider_name,
        "time_window.evaluation": evaluation_window,
        "time_window.delivery": delivery_window,
    }
    _sms_legacy_not_delivered_within.set(ratio, attributes)


def record_priority(
    priority: int,
    provider_name: str,
) -> None:
    attributes: dict[str, AttributeValue] = {
        "provider.name": provider_name,
    }
    _priority.set(priority, attributes)


def record_updated_at(
    updated_at: datetime.datetime,
    provider_name: str,
) -> None:
    attributes: dict[str, AttributeValue] = {
        "provider.name": provider_name,
    }
    _updated_at.set(updated_at.timestamp(), attributes)


def record_info(
    provider_name: str,
    active: bool,
    supports_international: bool,
    notification_type: str,
) -> None:
    attributes: dict[str, AttributeValue] = {
        "provider.name": provider_name,
        "provider.active": active,
        "provider.supports_international": supports_international,
        "notification.type": notification_type,
    }
    _info.set(1, attributes)
