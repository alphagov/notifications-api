import datetime
import functools
from collections.abc import Callable, Iterable, MutableMapping
from time import monotonic
from typing import Any

import flask
from notifications_utils.semconv import HTTP_DURATION_HISTOGRAM_BUCKETS, set_error_type
from opentelemetry.metrics import CallbackOptions, Observation, get_meter
from opentelemetry.util.types import AttributeValue


def _oneshot_gauge_next_observation_consumer(
    container: MutableMapping[str, Any], base_name: str
) -> Callable[[CallbackOptions], Iterable[Observation]]:
    def _consumer(opts: CallbackOptions) -> Iterable[Observation]:
        next_observations_name = base_name + "_next_observations"
        observations: tuple[Observation, ...] = container[next_observations_name]
        container[next_observations_name] = ()
        flask.current_app.logger.info("Observing %s observations: %s", len(observations), ",".join(str(obs.value) for obs in observations))
        return observations

    return _consumer


_meter = get_meter(__name__)

_request_duration = _meter.create_histogram(
    "provider.request.duration",
    unit="s",
    description="Duration of (HTTP) requests to providers",
    explicit_bucket_boundaries_advisory=HTTP_DURATION_HISTOGRAM_BUCKETS,
)

_sms_legacy_not_delivered_within = _meter.create_observable_gauge(
    "provider.sms.legacy.not_delivered_within",
    callbacks=(_oneshot_gauge_next_observation_consumer(globals(), "_sms_legacy_not_delivered_within"),),
    unit="1",
    description="Proportion of SMS messages sent in the last time_window.evaluation seconds "
    "that were not delivered within time_window.delivery seconds. BEWARE this is a flawed metric "
    "as it includes notifications sent too recently to be able to determine this for sensibly, "
    "however this is the measure currently used by the SMS provider balancer for better or "
    "worse.",
)
_sms_legacy_not_delivered_within_next_observations: tuple[Observation, ...] = ()

_sms_banded_not_delivered_within = _meter.create_observable_gauge(
    "provider.sms.banded.not_delivered_within",
    callbacks=(_oneshot_gauge_next_observation_consumer(globals(), "_sms_banded_not_delivered_within"),),
    unit="1",
    description="Proportion of SMS messages sent in a time window of length time_window.evaluation "
    "seconds (ending time_window.delay seconds before the time of measurement) which took more "
    "than time_window.delivery seconds to be delivered and for us to receive the receipt.",
)
_sms_banded_not_delivered_within_next_observations: tuple[Observation, ...] = ()

_sms_banded_not_delivered_within_absolute = _meter.create_observable_gauge(
    "provider.sms.banded.not_delivered_within_absolute",
    callbacks=(_oneshot_gauge_next_observation_consumer(globals(), "_sms_banded_not_delivered_within_absolute"),),
    unit="{notification}",
    description="Number of SMS messages sent in a time window of length time_window.evaluation "
    "seconds (ending time_window.delay seconds before the time of measurement) which took more "
    "than time_window.delivery seconds to be delivered and for us to receive the receipt.",
)
_sms_banded_not_delivered_within_absolute_next_observations: tuple[Observation, ...] = ()

_sms_banded_not_delivered_within_total = _meter.create_observable_gauge(
    "provider.sms.banded.not_delivered_within_total",
    callbacks=(_oneshot_gauge_next_observation_consumer(globals(), "_sms_banded_not_delivered_within_total"),),
    unit="{notification}",
    description="Number of SMS messages sent in a time window of length time_window.evaluation "
    "seconds (ending time_window.delay seconds before the time of measurement).",
)
_sms_banded_not_delivered_within_total_next_observations: tuple[Observation, ...] = ()

_sms_banded_not_delivered_within_weighted = _meter.create_observable_gauge(
    "provider.sms.banded.not_delivered_within_weighted",
    callbacks=(_oneshot_gauge_next_observation_consumer(globals(), "_sms_banded_not_delivered_within_weighted"),),
    unit="1",
    description="Weighted average of provider.sms.banded.not_delivered_within ratios using weights "
    'from SMS_SLOW_DELIVERY_BANDS. A provider is considered "slow" if this value exceeds '
    "SMS_SLOW_DELIVERY_THRESHOLD.",
)
_sms_banded_not_delivered_within_weighted_next_observations: tuple[Observation, ...] = ()

_priority = _meter.create_observable_gauge(
    "provider.priority",
    callbacks=(_oneshot_gauge_next_observation_consumer(globals(), "_priority"),),
    unit="1",
    description="Observed priority value of a Provider",
)
_priority_next_observations: tuple[Observation, ...] = ()

_updated_at = _meter.create_observable_gauge(
    "provider.updated_at",
    callbacks=(_oneshot_gauge_next_observation_consumer(globals(), "_updated_at"),),
    unit="s",
    description="Unix epoch timestamp of Provider's last update",
)
_updated_at_next_observations: tuple[Observation, ...] = ()

_info = _meter.create_observable_gauge(
    "provider.info",
    callbacks=(_oneshot_gauge_next_observation_consumer(globals(), "_info"),),
    unit="1",
    description="Observed metadata values of a Provider",
)
_info_next_observations: tuple[Observation, ...] = ()


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
    _sms_legacy_not_delivered_within_next_observations = (Observation(ratio, attributes),)


def record_sms_banded_not_delivered_within(
    ratio: float,
    slow_notifications: int,
    total_notifications: int,
    provider_name: str,
    delivered_within: float,
    sent_after_ago: float,
) -> None:
    attributes: dict[str, AttributeValue] = {
        "provider.name": provider_name,
        "time_window.evaluation": sent_after_ago - delivered_within,
        "time_window.delivery": delivered_within,
        "time_window.delay": delivered_within,
    }
    _sms_banded_not_delivered_within_next_observations = (Observation(ratio, attributes),)
    _sms_banded_not_delivered_within_absolute_next_observations = (Observation(slow_notifications, attributes),)
    _sms_banded_not_delivered_within_total_next_observations = (Observation(total_notifications, attributes),)


def record_sms_banded_not_delivered_within_weighted(
    weighted_ratio: float,
    provider_name: str,
) -> None:
    attributes: dict[str, AttributeValue] = {
        "provider.name": provider_name,
    }
    _sms_banded_not_delivered_within_weighted_next_observations = (Observation(weighted_ratio, attributes),)


def record_priority(
    priority: int,
    provider_name: str,
) -> None:
    attributes: dict[str, AttributeValue] = {
        "provider.name": provider_name,
    }
    _priority_next_observations = (Observation(priority, attributes),)


def record_updated_at(
    updated_at: datetime.datetime,
    provider_name: str,
) -> None:
    attributes: dict[str, AttributeValue] = {
        "provider.name": provider_name,
    }
    _updated_at_next_observations = (Observation(updated_at.timestamp(), attributes),)


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
    _info_next_observations = (Observation(1, attributes),)
