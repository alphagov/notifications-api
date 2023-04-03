import os
from functools import partial

from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration


def sentry_sampler(sampling_context, sample_rate=0):
    if sampling_context["parent_sampled"]:
        return 1

    return sample_rate


def init_performance_monitoring():
    environment = os.getenv("NOTIFY_ENVIRONMENT").lower()
    enable_apm = environment in {"development", "preview", "staging"}

    if enable_apm:
        if sentry_dsn := os.getenv("SENTRY_DSN"):
            import sentry_sdk

            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=environment,
                debug=False,
                integrations=[
                    FlaskIntegration(),
                    CeleryIntegration(),
                    SqlalchemyIntegration(),
                ],
                sample_rate=float(os.getenv("SENTRY_SAMPLE_RATE", 1.0)),  # Error sampling rate
                attach_stacktrace=False,  # Attach stacktraces to _all_ events (ie even log messages)
                send_default_pii=False,  # Don't include any default PII (false by default, here for explicitness)
                request_bodies="never",  # Include request body (eg POST payload) in sentry errors
                traces_sampler=partial(
                    sentry_sampler, sample_rate=float(os.getenv("SENTRY_TRACING_SAMPLE_RATE", 0))
                ),  # Custom decision-maker for sampling traces
            )
