import os


def init_performance_monitoring():
    environment = os.getenv("NOTIFY_ENVIRONMENT").lower()
    enable_apm = environment in {"development", "preview", "staging"}

    if environment == "production" and os.getenv("CF_INSTANCE_INDEX", "-1") == "9":
        # In production, turn it on for instance 9 (randomly chosen) only.
        enable_apm = True

    if enable_apm and (sentry_dsn := os.getenv("SENTRY_DSN")):
        import sentry_sdk

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            debug=False,
            # Error sampling rate
            sample_rate=float(os.getenv("SENTRY_SAMPLE_RATE", 1.0)),
            # Attach stacktraces to _all_ events (ie even log messages)
            attach_stacktrace=False,
            # Don't include any default PII (false by default, here for explicitness)
            send_default_pii=False,
            # Include request body (eg POST payload) in sentry errors
            request_bodies="never",
            # Float in range 0-1 representing % of requests to trace
            traces_sample_rate=float(os.getenv("SENTRY_TRACING_SAMPLE_RATE", 0)),
        )
