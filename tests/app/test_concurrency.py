import time as stdlib_time
from functools import partial

import pytest
from eventlet.green import time as green_time

from app.concurrency import run_concurrently


class TestRunConcurrently:
    def test_ordering_of_results_matches_input_order(self, notify_api):
        def sleep(duration):
            green_time.sleep(duration)
            return duration

        results = run_concurrently(
            partial(sleep, 0.05),
            partial(sleep, 0.04),
            partial(sleep, 0.03),
            partial(sleep, 0.02),
            partial(sleep, 0.01),
        )

        assert results == (0.05, 0.04, 0.03, 0.02, 0.01)

    # Mark this test as flaky. It's possible that some CPU hiccups could cause the test to artificially take
    # longer than expected. As long as at least one of the three runs is reasonably fast, we have proof that
    # the tasks are executing concurrently.
    @pytest.mark.flaky(max_runs=3, min_passes=1)
    def test_duration_indicates_actual_concurrency(self, notify_api):
        def sleep(duration):
            green_time.sleep(duration)
            return duration

        start = stdlib_time.perf_counter()
        run_concurrently(
            partial(sleep, 0.10),
            partial(sleep, 0.10),
            partial(sleep, 0.10),
            partial(sleep, 0.10),
            partial(sleep, 0.10),
            partial(sleep, 0.10),
            partial(sleep, 0.10),
            partial(sleep, 0.10),
            partial(sleep, 0.10),
            partial(sleep, 0.10),
        )
        end = stdlib_time.perf_counter()

        assert (
            0.1 <= end - start <= 0.2
        ), "This should take about 0.1s to run - all of the functions should be sleeping together"
