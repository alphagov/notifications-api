import uuid
from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture

from app.load_shedding import (
    ServiceUnavailableError,
    ServiceVolumeTracker,
    check_load_shedding,
    is_worker_overloaded,
    should_throttle_service,
)

if TYPE_CHECKING:
    from flask import Flask

    from app.models import Service


class TestIsWorkerOverloaded:
    def test_returns_false_when_worker_not_overloaded(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mock_counter = mocker.patch("app.load_shedding.concurrent_request_counter")
        mock_counter.get.return_value = 10  # Below high water mark
        mock_gauge = mocker.patch("app.load_shedding.WORKER_LOAD_SHEDDING")

        assert is_worker_overloaded() is False

        # Should set gauge to 0 when not overloaded
        mock_gauge.set.assert_called_once_with(0)

    def test_returns_false_when_below_high_water_mark(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mock_counter = mocker.patch("app.load_shedding.concurrent_request_counter")
        mock_counter.get.return_value = 20  # Below HIGH_WATER_MARK of 26
        mock_gauge = mocker.patch("app.load_shedding.WORKER_LOAD_SHEDDING")

        assert is_worker_overloaded() is False

        # Should set gauge to 0
        mock_gauge.set.assert_called_once_with(0)

    def test_returns_true_when_above_high_water_mark(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mock_counter = mocker.patch("app.load_shedding.concurrent_request_counter")
        mock_counter.get.return_value = 28  # Above HIGH_WATER_MARK of 26
        mock_gauge = mocker.patch("app.load_shedding.WORKER_LOAD_SHEDDING")

        assert is_worker_overloaded() is True

        # Should set gauge to 1 when overloaded
        mock_gauge.set.assert_called_once_with(1)

    def test_returns_false_at_boundary(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mock_counter = mocker.patch("app.load_shedding.concurrent_request_counter")
        mock_counter.get.return_value = 26  # At HIGH_WATER_MARK
        mock_gauge = mocker.patch("app.load_shedding.WORKER_LOAD_SHEDDING")

        # At the threshold should NOT trigger (uses > not >=)
        assert is_worker_overloaded() is False

        # Should set gauge to 0 at boundary
        mock_gauge.set.assert_called_once_with(0)

    def test_increments_activation_counter_on_state_transition(
        self, notify_api: "Flask", mocker: MockerFixture
    ) -> None:
        """Test that counter increments ONCE when entering load shedding."""
        mock_counter = mocker.patch("app.load_shedding.concurrent_request_counter")
        mock_gauge = mocker.patch("app.load_shedding.WORKER_LOAD_SHEDDING")
        mock_activation_counter = mocker.patch("app.load_shedding.LOAD_SHEDDING_ACTIVATIONS")

        # Reset global state
        import app.load_shedding as ls_module

        ls_module._is_currently_load_shedding = False

        # First call: healthy (10 < 26)
        mock_counter.get.return_value = 10
        is_worker_overloaded()
        assert mock_activation_counter.inc.call_count == 0
        assert mock_gauge.set.call_args[0][0] == 0  # Gauge set to 0

        # Second call: enter overload (28 > 26) - should increment
        mock_counter.get.return_value = 28
        is_worker_overloaded()
        assert mock_activation_counter.inc.call_count == 1
        assert mock_gauge.set.call_args[0][0] == 1  # Gauge set to 1

        # Third call: stay overloaded (30 > 26) - should NOT increment again
        mock_counter.get.return_value = 30
        is_worker_overloaded()
        assert mock_activation_counter.inc.call_count == 1  # Still 1, not 2
        assert mock_gauge.set.call_args[0][0] == 1  # Gauge still 1

        # Fourth call: exit overload (10 < 26) - should NOT increment
        mock_counter.get.return_value = 10
        is_worker_overloaded()
        assert mock_activation_counter.inc.call_count == 1
        assert mock_gauge.set.call_args[0][0] == 0  # Gauge back to 0

        # Fifth call: re-enter overload (28 > 26) - should increment again
        mock_counter.get.return_value = 28
        is_worker_overloaded()
        assert mock_activation_counter.inc.call_count == 2
        assert mock_gauge.set.call_args[0][0] == 1  # Gauge set to 1 again

    def test_logs_activation_and_deactivation(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        """Test that state transitions are logged."""
        mock_counter = mocker.patch("app.load_shedding.concurrent_request_counter")
        mocker.patch("app.load_shedding.WORKER_LOAD_SHEDDING")
        mocker.patch("app.load_shedding.LOAD_SHEDDING_ACTIVATIONS")

        # Reset global state
        import app.load_shedding as ls_module

        ls_module._is_currently_load_shedding = False

        # Enter load shedding - should log warning
        mock_counter.get.return_value = 28
        with notify_api.app_context():
            mock_logger = mocker.patch("app.load_shedding.current_app.logger")
            is_worker_overloaded()

            # Verify activation warning was logged
            mock_logger.warning.assert_called_once()
            assert "ACTIVATED" in mock_logger.warning.call_args[0][0]

        # Exit load shedding - should log info
        mock_counter.get.return_value = 10
        with notify_api.app_context():
            mock_logger = mocker.patch("app.load_shedding.current_app.logger")
            is_worker_overloaded()

            # Verify deactivation info was logged
            mock_logger.info.assert_called_once()
            assert "DEACTIVATED" in mock_logger.info.call_args[0][0]

    def test_sets_gauge_to_zero_on_error(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        """Test that gauge is set to 0 when an error occurs."""
        mock_counter = mocker.patch("app.load_shedding.concurrent_request_counter")
        mock_counter.get.side_effect = Exception("Test error")
        mock_gauge = mocker.patch("app.load_shedding.WORKER_LOAD_SHEDDING")

        # Should not raise, should return False
        assert is_worker_overloaded() is False

        # Should set gauge to 0 on error
        mock_gauge.set.assert_called_once_with(0)


class TestShouldThrottleService:
    def test_returns_false_when_worker_not_overloaded(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=False)

        service_id = str(uuid.uuid4())
        assert should_throttle_service(service_id) is False

    def test_returns_false_when_no_service_volumes_tracked(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)

        # Mock the tracker to return empty volumes
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")
        mock_tracker.get_volumes.return_value = {}

        service_id = str(uuid.uuid4())
        assert should_throttle_service(service_id) is False

    def test_throttles_service_contributing_significant_pct(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)

        # Simulate: 1 service with 1000 requests, 100 services with 5 requests each
        # Total: 1500 requests, spammer contributes 66.7%
        service_volumes = {"spammer": 1000}
        service_volumes.update({f"service-{i}": 5 for i in range(100)})

        # Mock the tracker to return our test data
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")
        mock_tracker.get_volumes.return_value = service_volumes

        # Spammer contributing 66.7% should be throttled (>20% threshold)
        assert should_throttle_service("spammer") is True

        # Normal services contributing 0.33% should NOT be throttled
        assert should_throttle_service("service-0") is False

    def test_throttles_service_with_volume_above_median_multiple(
        self, notify_api: "Flask", mocker: MockerFixture
    ) -> None:
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)

        # Simulate: 10 services with 10 requests each, 1 service with 200 requests
        # Median = 10, outlier = 200 (20x median)
        service_volumes = {f"service-{i}": 10 for i in range(10)}
        service_volumes["outlier"] = 200

        # Mock the tracker to return our test data
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")
        mock_tracker.get_volumes.return_value = service_volumes

        # Outlier at 20x median should be throttled (>10x threshold)
        assert should_throttle_service("outlier") is True

        # Normal services at median should NOT be throttled
        assert should_throttle_service("service-0") is False

    def test_single_service_contributing_100_pct(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)

        # Test with single service (contributes 100% of load)
        # Should be throttled by contribution % (100% > 20% threshold)
        service_volumes = {"single": 50}

        # Mock the tracker to return our test data
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")
        mock_tracker.get_volumes.return_value = service_volumes

        # Single service contributing 100% should be throttled (exceeds 20% threshold)
        assert should_throttle_service("single") is True

    def test_returns_false_on_error(self, notify_api: "Flask", mocker: MockerFixture) -> None:
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)

        # Mock the tracker to raise an exception
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")
        mock_tracker.get_volumes.side_effect = Exception("Tracker error")

        service_id = str(uuid.uuid4())
        # Should not raise, should return False on error
        assert should_throttle_service(service_id) is False


class TestServiceVolumeTracker:
    def test_tracks_requests_in_memory(self) -> None:
        tracker = ServiceVolumeTracker(window_seconds=60.0)
        service_id = str(uuid.uuid4())

        tracker.track_request(service_id)
        tracker.track_request(service_id)
        tracker.track_request(service_id)

        volumes = tracker.get_volumes()
        assert volumes[service_id] == 3

    def test_sliding_window_cleanup(self, mocker: MockerFixture) -> None:
        tracker = ServiceVolumeTracker(window_seconds=2.0)  # 2-second window for testing
        service_id = str(uuid.uuid4())

        # Mock time to control when requests happen
        mock_time = mocker.patch("app.load_shedding.time")

        # Add 3 requests at t=0
        mock_time.time.return_value = 100.0
        tracker.track_request(service_id)
        tracker.track_request(service_id)
        tracker.track_request(service_id)

        # At t=0, should see 3 requests
        volumes = tracker.get_volumes()
        assert volumes[service_id] == 3

        # At t=3 (beyond 2-second window), should see 0 requests
        mock_time.time.return_value = 103.0
        volumes = tracker.get_volumes()
        assert service_id not in volumes  # Old entries removed

    def test_multiple_services(self) -> None:
        tracker = ServiceVolumeTracker(window_seconds=60.0)

        service1 = str(uuid.uuid4())
        service2 = str(uuid.uuid4())
        service3 = str(uuid.uuid4())

        # Different request volumes
        for _ in range(10):
            tracker.track_request(service1)
        for _ in range(5):
            tracker.track_request(service2)
        tracker.track_request(service3)

        volumes = tracker.get_volumes()
        assert volumes[service1] == 10
        assert volumes[service2] == 5
        assert volumes[service3] == 1

    def test_memory_cleanup_removes_empty_services(self, mocker: MockerFixture) -> None:
        tracker = ServiceVolumeTracker(window_seconds=1.0)
        service_id = str(uuid.uuid4())

        mock_time = mocker.patch("app.load_shedding.time")

        # Add request at t=0
        mock_time.time.return_value = 100.0
        tracker.track_request(service_id)
        assert service_id in tracker._requests

        # At t=2, request is outside window
        mock_time.time.return_value = 102.0
        volumes = tracker.get_volumes()

        # Should clean up empty service from memory
        assert service_id not in tracker._requests
        assert service_id not in volumes


class TestCheckLoadShedding:
    def test_does_nothing_when_worker_not_overloaded(
        self, notify_api: "Flask", mocker: MockerFixture, sample_service: "Service"
    ) -> None:
        notify_api.config["LOAD_SHEDDING_ENABLED"] = True
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=False)
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")

        # Should not raise
        check_load_shedding(sample_service)

        # Should still track the request
        mock_tracker.track_request.assert_called_once_with(str(sample_service.id))

    def test_throttles_high_volume_service_when_overloaded(
        self, notify_api: "Flask", mocker: MockerFixture, sample_service: "Service"
    ) -> None:
        notify_api.config["LOAD_SHEDDING_ENABLED"] = True
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)
        mocker.patch("app.load_shedding.should_throttle_service", return_value=True)
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")

        # Need to mock before check_load_shedding imports it
        from app import statsd_client

        mock_statsd_incr = mocker.patch.object(statsd_client, "incr")

        with pytest.raises(ServiceUnavailableError) as exc:
            check_load_shedding(sample_service)

        assert exc.value.service_id == str(sample_service.id)
        assert exc.value.retry_after == 5

        # Should track the request and metrics
        mock_tracker.track_request.assert_called_once_with(str(sample_service.id))
        mock_statsd_incr.assert_called_once_with(f"load_shedding.throttled.{sample_service.id}")

    def test_allows_low_volume_service_when_overloaded(
        self, notify_api: "Flask", mocker: MockerFixture, sample_service: "Service"
    ) -> None:
        notify_api.config["LOAD_SHEDDING_ENABLED"] = True
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)
        mocker.patch("app.load_shedding.should_throttle_service", return_value=False)
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")

        # Should not raise
        check_load_shedding(sample_service)

        # Should still track the request
        mock_tracker.track_request.assert_called_once_with(str(sample_service.id))

    def test_does_nothing_when_load_shedding_disabled(
        self, notify_api: "Flask", mocker: MockerFixture, sample_service: "Service"
    ) -> None:
        # Disable load shedding in config
        notify_api.config["LOAD_SHEDDING_ENABLED"] = False

        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)
        mocker.patch("app.load_shedding.should_throttle_service", return_value=True)
        mock_tracker = mocker.patch("app.load_shedding._volume_tracker")

        # Should not raise even though conditions would normally throttle
        check_load_shedding(sample_service)

        # Should not track when disabled
        mock_tracker.track_request.assert_not_called()

    def test_integrates_with_rate_limiting_flow(
        self, notify_api: "Flask", mocker: MockerFixture, sample_service: "Service"
    ) -> None:
        """Test that load shedding works end-to-end when conditions are met."""
        # Enable load shedding
        notify_api.config["LOAD_SHEDDING_ENABLED"] = True

        # Mock the load shedding conditions to trigger throttling
        mocker.patch("app.load_shedding.is_worker_overloaded", return_value=True)
        mocker.patch("app.load_shedding.should_throttle_service", return_value=True)
        mocker.patch("app.load_shedding._volume_tracker")

        # Mock statsd
        from app import statsd_client

        mock_statsd_incr = mocker.patch.object(statsd_client, "incr")

        # Should raise ServiceUnavailableError when load shedding is triggered
        with pytest.raises(ServiceUnavailableError) as exc_info:
            check_load_shedding(sample_service)

        # Verify the exception has correct attributes
        assert exc_info.value.service_id == str(sample_service.id)
        assert exc_info.value.retry_after == 5
        assert "temporarily unavailable" in exc_info.value.message.lower()

        # Verify metrics were recorded
        mock_statsd_incr.assert_called_once_with(f"load_shedding.throttled.{sample_service.id}")
