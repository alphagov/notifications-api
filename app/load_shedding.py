"""
Load shedding to protect low-volume services during high spike traffic which will trigger
autoscaling.

When a worker is overloaded (> HIGH_WATER_MARK concurrent requests), throttle high-volume
services to protect low-volume services during the autoscaling window (~1 minute).
"""

import time
from collections import deque
from typing import TYPE_CHECKING

from flask import current_app
from gds_metrics.metrics import Counter, Gauge

from app import concurrent_request_counter

if TYPE_CHECKING:
    from app.models import Service

# Gauge to track if THIS worker is currently in load shedding mode
# When scraped across all workers, sum gives total workers load shedding
WORKER_LOAD_SHEDDING = Gauge(
    "worker_load_shedding_active",
    "Whether this worker is currently in load shedding mode (1=active, 0=inactive)",
)

# Counter to track activation events (entering load shedding)
# Incremented once per transition from healthy → overloaded
LOAD_SHEDDING_ACTIVATIONS = Counter(
    "load_shedding_activations_total",
    "Number of times this worker entered load shedding mode",
)

# Track current state to detect transitions
_is_currently_load_shedding = False


class ServiceVolumeTracker:
    """Per-worker in-memory tracking of request volumes using sliding window.

    Tracks requests in-memory for this worker only. Each worker independently
    monitors which services are consuming its capacity.

    """

    def __init__(self, window_seconds: float = 60.0) -> None:
        """Initialize tracker with sliding window.

        Args:
            window_seconds: How many seconds of history to track (default 60)
        """
        self._requests: dict[str, deque[float]] = {}
        self._window = window_seconds
        self._last_cleanup = 0.0
        self._cleanup_interval = window_seconds

    def track_request(self, service_id: str) -> None:
        """Record a request from this service.

        Args:
            service_id: ID of the service making the request
        """
        now = time.time()
        if service_id not in self._requests:
            self._requests[service_id] = deque()

        self._requests[service_id].append(now)

        # Lazy cleanup of old entries to keep memory bounded
        self._cleanup_old_entries(service_id, now)

        # Periodic cleanup across all services to avoid unbounded growth
        if now - self._last_cleanup >= self._cleanup_interval:
            self._cleanup_all(now)
            self._last_cleanup = now

    def _cleanup_old_entries(self, service_id: str, now: float) -> None:
        """Remove entries older than the window.

        Args:
            service_id: Service to clean up
            now: Current timestamp
        """
        cutoff = now - self._window
        queue = self._requests[service_id]
        while queue and queue[0] < cutoff:
            queue.popleft()

        # Clean up empty deques to free memory
        if not queue:
            del self._requests[service_id]

    def _cleanup_all(self, now: float) -> None:
        """Remove expired entries for all services.

        Args:
            now: Current timestamp
        """
        cutoff = now - self._window

        for service_id in list(self._requests.keys()):
            queue = self._requests[service_id]
            while queue and queue[0] < cutoff:
                queue.popleft()

            if not queue:
                del self._requests[service_id]

    def get_volumes(self) -> dict[str, int]:
        """Get current volumes for all services that have recent requests.

        Returns:
            Dict mapping service_id -> request count in the window
        """
        now = time.time()
        cutoff = now - self._window

        volumes = {}
        # Clean up all services while building volume map
        for service_id in list(self._requests.keys()):
            timestamps = self._requests[service_id]

            # Remove old entries
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            # Only include services with recent requests
            if timestamps:
                volumes[service_id] = len(timestamps)
            else:
                # Clean up empty deques
                del self._requests[service_id]

        return volumes


# Global tracker instance per worker
_volume_tracker = ServiceVolumeTracker(window_seconds=60.0)


class ServiceUnavailableError(Exception):
    """
    Raised when system is overloaded and high-volume services are being throttled
    to protect low-volume services during autoscaling.

    Returns 429 with Retry-After: 5 header. Clients should:
    - Wait 5 seconds before retrying
    - Implement exponential backoff if multiple 429s occur
    - Consider circuit breaker pattern for persistent failures

    Note: ALB distributes retries across all workers, so a 429 from one
    worker doesn't mean all workers are overloaded.
    """

    def __init__(self, service_id: str, retry_after: int = 5) -> None:
        self.service_id = service_id
        self.retry_after = retry_after
        self.message = "Service temporarily unavailable due to high demand. Please retry shortly."
        self.code = 429
        super().__init__(self.message)
        self.status_code = 429

    def to_dict_v2(self) -> dict[str, int | list[dict[str, str]]]:
        return {
            "status_code": 429,
            "errors": [{"error": "ServiceUnavailable", "message": self.message}],
        }

    def __str__(self) -> str:
        return f"ServiceUnavailableError: service_id={self.service_id}; retry_after={self.retry_after}; {self.message}"


def is_worker_overloaded() -> bool:
    """
    Check if THIS worker is at high water mark.

    Each worker independently protects itself when it reaches capacity.
    No coordination needed - ALB will distribute retries to healthy workers.

    Returns:
        bool: True if this worker is overloaded, False otherwise
    """
    global _is_currently_load_shedding

    try:
        current_load = concurrent_request_counter.get()
        high_water_mark = current_app.config.get("HIGH_WATER_MARK", 26)

        is_overloaded = current_load > high_water_mark

        # Track state transitions to count activation events
        if is_overloaded and not _is_currently_load_shedding:
            # Entering load shedding - increment counter once
            LOAD_SHEDDING_ACTIVATIONS.inc()
            _is_currently_load_shedding = True
            current_app.logger.warning(
                "Load shedding ACTIVATED: worker exceeded HIGH_WATER_MARK (%s/%s concurrent requests)",
                current_load,
                high_water_mark,
            )
        elif not is_overloaded and _is_currently_load_shedding:
            # Exiting load shedding
            _is_currently_load_shedding = False
            current_app.logger.info(
                "Load shedding DEACTIVATED: worker below HIGH_WATER_MARK (%s/%s concurrent requests)",
                current_load,
                high_water_mark,
            )

        # Update gauge (current state)
        WORKER_LOAD_SHEDDING.set(1 if is_overloaded else 0)

        return is_overloaded
    except Exception as e:
        current_app.logger.error("Error checking worker overload: %s", e)
        # On error, assume not overloaded to avoid false positives
        WORKER_LOAD_SHEDDING.set(0)
        _is_currently_load_shedding = False
        return False


def should_throttle_service(service_id: str) -> bool:
    """
    Determine if a service should be throttled based on contribution to load.
    Only throttles when worker is overloaded AND service meets one of:
    1. Contributing >= THROTTLE_CONTRIBUTION_PCT% of total volume (catches single spammers)
    2. Volume >= THROTTLE_VOLUME_MEDIAN_MULTIPLE times the median (catches outliers)

    Args:
        service_id: ID of the service to check (string)

    Returns:
        bool: True if service should be throttled, False otherwise
    """
    # First check if THIS worker is overloaded
    if not is_worker_overloaded():
        return False  # Worker healthy, no throttling needed

    try:
        # Get volumes from in-memory tracker
        service_volumes = _volume_tracker.get_volumes()

        if not service_volumes:
            return False

        current_volume = service_volumes.get(service_id, 0)
        if current_volume == 0:
            return False

        # Calculate total volume and contribution percentage
        total_volume = sum(service_volumes.values())
        contribution_pct = (current_volume / total_volume * 100) if total_volume > 0 else 0

        # Check if contributing a significant % of load
        throttle_contribution_pct = current_app.config.get("THROTTLE_CONTRIBUTION_PCT", 20)
        if contribution_pct >= throttle_contribution_pct:
            current_app.logger.info(
                "Service %s contributing %.1f%% of load (%s/%s requests)",
                service_id,
                contribution_pct,
                current_volume,
                total_volume,
            )
            return True

        # Check if volume is significantly above median (outlier detection)
        volumes = sorted(service_volumes.values())
        median_volume = volumes[len(volumes) // 2]
        throttle_median_multiple = current_app.config.get("THROTTLE_VOLUME_MEDIAN_MULTIPLE", 10)

        if median_volume > 0 and current_volume >= (median_volume * throttle_median_multiple):
            current_app.logger.info(
                "Service %s volume %s is %.1fx median (%s)",
                service_id,
                current_volume,
                current_volume / median_volume,
                median_volume,
            )
            return True

        return False
    except Exception as e:
        current_app.logger.error("Error checking service throttle for %s: %s", service_id, e)
        # On error, don't throttle to avoid false positives
        return False


def check_load_shedding(service: "Service") -> None:
    """
    Check if this service should be throttled due to worker overload.

    Called from validators.check_rate_limiting() after normal rate limit checks.

    Args:
        service: The authenticated service object

    Raises:
        ServiceUnavailableError: If service should be throttled
    """
    if not current_app.config.get("LOAD_SHEDDING_ENABLED", False):
        return

    service_id = str(service.id)

    # Track this request in-memory
    _volume_tracker.track_request(service_id)

    # Check if we should throttle
    if should_throttle_service(service_id):
        from app import statsd_client

        # Track throttling event
        statsd_client.incr(f"load_shedding.throttled.{service_id}")

        # Log throttling action
        current_app.logger.warning(
            "Load shedding: Throttling service %s (%s) due to worker overload. "
            "Service is in top volume percentile during scale-up.",
            service_id,
            service.name,
        )

        raise ServiceUnavailableError(service_id=service_id, retry_after=5)
