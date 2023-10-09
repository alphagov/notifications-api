import os
from functools import partial


def sentry_sampler(sampling_context, sample_rate: float = 0.0):
    if sampling_context["parent_sampled"]:
        return 1

    return sample_rate


def init_performance_monitoring():
    environment = os.getenv("NOTIFY_ENVIRONMENT").lower()
    not_production = environment in {"development", "preview", "staging"}
    sentry_enabled = bool(int(os.getenv("SENTRY_ENABLED", "0")))
    sentry_dsn = os.getenv("SENTRY_DSN")

    if environment and sentry_enabled and sentry_dsn:
        import sentry_sdk

        error_sample_rate = float(os.getenv("SENTRY_ERRORS_SAMPLE_RATE", 0.0))
        trace_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", 0.0))

        send_pii = True if not_production else False
        send_request_bodies = "medium" if not_production else "never"

        # Enable tracing requests on only a single API instance in production while we check performance there.
        if not_production or os.getenv("CF_INSTANCE_INDEX", "-1") in {"1", "2", "3", "4", "5"}:
            traces_sampler = partial(sentry_sampler, sample_rate=trace_sample_rate)
        else:
            traces_sampler = None

        try:
            from app.version import __git_commit__

            release = __git_commit__
        except ImportError:
            release = None

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            sample_rate=error_sample_rate,
            send_default_pii=send_pii,
            request_bodies=send_request_bodies,
            traces_sampler=traces_sampler,
            release=release,
        )

        if app_name := os.getenv("NOTIFY_APP_NAME"):
            sentry_sdk.set_tag("app", app_name)
