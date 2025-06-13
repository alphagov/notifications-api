import os

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.processor.baggage import ALLOW_ALL_BAGGAGE_KEYS, BaggageSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import (
    Span,
    get_tracer_provider,
    set_tracer_provider,
)


class Traces:
    def __init__(self):
        self.tracer = None

    def init_app(self, app):
        export_mode = app.config.get("OTEL_EXPORT_TYPE", "none").lower()
        resource = Resource.create({"service.name": os.getenv("NOTIFY_APP_NAME", app.config.get("NOTIFY_APP_NAME"))})
        set_tracer_provider(TracerProvider(resource=resource))
        get_tracer_provider().get_tracer(app.config.get("NOTIFY_APP_NAME"))

        span_processor = None

        if export_mode == "console":
            span_processor = BatchSpanProcessor(ConsoleSpanExporter())
        elif export_mode == "otlp":
            endpoint = app.config.get("OTEL_COLLECTOR_ENDPOINT", "localhost:4317")
            span_processor = BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=endpoint,
                    insecure=True,
                )
            )

        if span_processor:
            # Instead of adding all baggage to attributes, we could do something like
            # regex_predicate = lambda baggage_key: baggage_key.startswith("^key.+")
            # tracer_provider.add_span_processor(BaggageSpanProcessor(regex_predicate))
            get_tracer_provider().add_span_processor(BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS))
            get_tracer_provider().add_span_processor(span_processor)

            # not sure I like the instumentation here as it adds both traces and metrics

            self.instrument_app(app)

    def instrument_app(self, app):
        instrumentation = app.config.get("OTEL_INSTRUMENTATIONS", "").lower().split(",")

        if "wsgi" in instrumentation:
            self.instrument_app_wsgi(app)

        if "celery" in instrumentation:
            from opentelemetry.instrumentation.celery import CeleryInstrumentor

            CeleryInstrumentor().instrument()
        if "flask" in instrumentation:
            from opentelemetry.instrumentation.flask import FlaskInstrumentor

            FlaskInstrumentor().instrument_app(app)
        if "redis" in instrumentation:
            from opentelemetry.instrumentation.redis import RedisInstrumentor

            RedisInstrumentor().instrument()
        if "requests" in instrumentation:
            from opentelemetry.instrumentation.requests import RequestsInstrumentor

            RequestsInstrumentor().instrument()
        if "sqlalchemy" in instrumentation:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument(enable_commenter=True, commenter_options={})
        if "psycopg2" in instrumentation:
            from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

            Psycopg2Instrumentor().instrument(enable_commenter=True, commenter_options={})
        if "boto3sqs" in instrumentation:
            from opentelemetry.instrumentation.boto3sqs import Boto3SQSInstrumentor

            Boto3SQSInstrumentor().instrument()

    def instrument_app_wsgi(self, app):
        from wsgiref.types import WSGIEnvironment

        from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

        def request_hook(span: Span, environ: WSGIEnvironment):
            if span and span.is_recording():
                span.set_attribute("custom_user_attribute_from_request_hook", "some-value")

        def response_hook(span: Span, environ: WSGIEnvironment, status: str, response_headers: list[tuple[str, str]]):
            if span and span.is_recording():
                span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

        app.wsgi_app = OpenTelemetryMiddleware(app.wsgi_app, request_hook=request_hook, response_hook=response_hook)


otel_traces = Traces()
