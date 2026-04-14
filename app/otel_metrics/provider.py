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
