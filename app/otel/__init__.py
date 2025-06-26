import os

from flask import Flask
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.processor.baggage import ALLOW_ALL_BAGGAGE_KEYS, BaggageSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import get_tracer_provider, set_tracer_provider


def init_otel_app(app: Flask) -> None:
    """
    Initialize the OpenTelemetry instrumentation for the Flask app.
    """

    if getattr(app, "_otel_instrumented", False):
        app.logger.debug("OpenTelemetry instrumentation already applied, skipping.")
        return

    export_mode = app.config.get("OTEL_EXPORT_TYPE", "none").lower().strip()
    metric_readers = []

    if export_mode == "console":
        app.logger.info("OpenTelemetry metrics and spans will be exported to console")
        metric_readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))
        span_processor = BatchSpanProcessor(ConsoleSpanExporter())
    elif export_mode == "otlp":
        endpoint = app.config.get("OTEL_COLLECTOR_ENDPOINT", "localhost:4317")
        app.logger.info("OpenTelemetry metrics and spans will be exported to OTLP collector at %s", endpoint)
        otlp_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        # Instead of adding all baggage to attributes, we could do something like
        # regex_predicate = lambda baggage_key: baggage_key.startswith("^key.+")
        # tracer_provider.add_span_processor(BaggageSpanProcessor(regex_predicate))
        metric_readers.append(PeriodicExportingMetricReader(otlp_exporter))
        # Metrics will be exported every 60 seconds with a 30 seconds timeout by default.
        # The following environments variables can be used to change this:
        # OTEL_METRIC_EXPORT_INTERVAL
        # OTEL_METRIC_EXPORT_TIMEOUT
        span_processor = BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=endpoint,
                insecure=app.config.get("OTEL_COLLECTOR_INSECURE", True),
            )
        )
    elif export_mode == "none":
        app.logger.info("OpenTelemetry metrics and spans will not be exported")
        return
    else:
        raise ValueError(f"Invalid OTEL_EXPORT_TYPE: {export_mode}. Expected 'console', 'otlp', or 'none'.")

    resource = Resource.create(
        {"service.name": os.getenv("NOTIFY_APP_NAME") or app.config.get("NOTIFY_APP_NAME") or "notifications"}
    )

    provider = MeterProvider(metric_readers=metric_readers, resource=resource)
    metrics.set_meter_provider(provider)

    set_tracer_provider(TracerProvider(resource=resource))
    get_tracer_provider().add_span_processor(BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS))
    get_tracer_provider().add_span_processor(span_processor)

    _instrument_app(app)

    app._otel_instrumented = True


def _instrument_app(app: Flask) -> None:
    """
    Apply OpenTelemetry instrumentation
    """

    instrument_map = {
        "wsgi": (_instrument_wsgi, "WSGI"),
        "celery": (_instrument_celery, "Celery"),
        "flask": (_instrument_flask, "Flask"),
        "redis": (_instrument_redis, "Redis"),
        "requests": (_instrument_requests, "Requests"),
        "sqlalchemy": (_instrument_sqlalchemy, "SQLAlchemy"),
        "psycopg2": (_instrument_psycopg2, "Psycopg2"),
        "boto3sqs": (_instrument_boto3sqs, "Boto3SQS"),
        "botocore": (_instrument_botocore, "Botocore"),
    }

    instrumentation = [i.strip() for i in app.config.get("OTEL_INSTRUMENTATIONS", "").lower().split(",") if i.strip()]

    unsupported = set(instrumentation) - set(instrument_map.keys())
    if unsupported:
        raise ValueError(
            f"Unsupported OpenTelemetry instrumentations requested: {', '.join(sorted(unsupported))}. "
            f"Supported: {', '.join(sorted(instrument_map.keys()))}"
        )

    for name in instrumentation:
        func, label = instrument_map[name]
        try:
            func(app)
        except ImportError:
            app.logger.warning("%s instrumentation requested but not installed.", label)


def _instrument_wsgi(app: Flask) -> None:
    from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

    app.wsgi_app = OpenTelemetryMiddleware(app.wsgi_app)


def _instrument_celery(app: Flask) -> None:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    CeleryInstrumentor().instrument()


def _instrument_flask(app: Flask) -> None:
    from opentelemetry.instrumentation.flask import FlaskInstrumentor

    FlaskInstrumentor().instrument_app(app)


def _instrument_redis(app: Flask) -> None:
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    # Work around for span names not being unique in Redis instrumentation
    def redis_response_hook(span, *args, **kwargs):
        if span:
            span.update_name(f"redis/{span.name}")

    RedisInstrumentor().instrument(response_hook=redis_response_hook)


def _instrument_requests(app: Flask) -> None:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    # Work around for span names not being unique in Requests instrumentation
    def requests_response_hook(span, *args, **kwargs):
        if span:
            span.update_name(f"requests/{span.name}")

    RequestsInstrumentor().instrument(response_hook=requests_response_hook)


def _instrument_sqlalchemy(app: Flask) -> None:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(enable_commenter=True, commenter_options={})


def _instrument_psycopg2(app: Flask) -> None:
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

    Psycopg2Instrumentor().instrument(enable_commenter=True, commenter_options={})


def _instrument_boto3sqs(app: Flask) -> None:
    from opentelemetry.instrumentation.boto3sqs import Boto3SQSInstrumentor

    Boto3SQSInstrumentor().instrument()


def _instrument_botocore(app: Flask) -> None:
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

    BotocoreInstrumentor().instrument()
