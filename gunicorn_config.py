import os

from notifications_utils.gunicorn_defaults import set_gunicorn_defaults

set_gunicorn_defaults(globals())


# importing child_exit from gds_metrics.gunicorn has the side effect of eagerly importing
# prometheus_client, flask, werkzeug and more, which is a bad idea to do before eventlet
# has done its monkeypatching. use a nested import for the rare cases child_exit is actually
# called instead.
def child_exit(server, worker):
    from prometheus_client import multiprocess

    multiprocess.mark_process_dead(worker.pid)


workers = 4
worker_class = "eventlet"
worker_connections = 8  # limit runaway greenthread creation
statsd_host = "{}:8125".format(os.getenv("STATSD_HOST"))
keepalive = 0  # disable temporarily for diagnosing issues
timeout = int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30))  # though has little effect with eventlet worker_class

debug_post_threshold = os.getenv("NOTIFY_GUNICORN_DEBUG_POST_REQUEST_LOG_THRESHOLD_SECONDS", None)
if debug_post_threshold:
    debug_post_threshold_float = float(debug_post_threshold)
    profiler = None

    def pre_request(worker, req):
        # using os.times() to avoid additional imports before eventlet monkeypatching
        req._pre_request_elapsed = os.times().elapsed

    def _tuples_to_lists(value):
        if isinstance(value, tuple):
            # convert to list for more compact (and json-able) representation
            return list(value)

        return value

    def post_request(worker, req, environ, resp):
        elapsed = os.times().elapsed - req._pre_request_elapsed
        if elapsed > debug_post_threshold_float:
            import json
            import time
            from io import StringIO
            from os import getpid
            from pstats import Stats

            import psutil
            from eventlet.green import profile

            # consume this iterator to give cpu_percent calculation a "start time" to work with
            list(psutil.process_iter(["cpu_percent"]))

            global profiler
            if profiler is None:
                profiler = profile.Profile()

            should_profile = not getattr(profiler, "running", False)
            if should_profile:
                profiler.start()

            perf_counter_before = time.perf_counter()

            time.sleep(0.1)  # period over which to profile and calculate cpu_percent

            perf_counter_after = time.perf_counter()

            if should_profile:
                profiler.stop()
                prof_out_sio = StringIO()
                s = Stats(profiler, stream=prof_out_sio)
                s.sort_stats("cumulative")
                s.print_stats(0.1)
                prof_out_str = prof_out_sio.getvalue()
            else:
                prof_out_str = "profiler already running - no profile collected"

            attrs = ["pid", "name", "cpu_percent", "status", "memory_info"]

            context = {
                "actual_profile_period": perf_counter_after - perf_counter_before,
                "request_time": elapsed,
                "processes": json.dumps(
                    [
                        attrs,
                        [[_tuples_to_lists(p.info[a]) for a in attrs] for p in psutil.process_iter(attrs)],
                    ]
                ),
                "profile": prof_out_str,
                "process_": getpid(),
            }
            worker.log.info(
                "post-request diagnostics for request of %(request_time)ss",
                context,
                extra=context,
            )
