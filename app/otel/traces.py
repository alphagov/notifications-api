from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import (
    get_tracer_provider,
    set_tracer_provider,
)


class Traces:
    def __init__(self):
        self.tracer = None

    def init_app(self, app):
        export_mode = app.config.get("OTEL_METRICS_EXPORT", "none").lower()
        set_tracer_provider(TracerProvider())
        get_tracer_provider().get_tracer("notifications-api")

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
            get_tracer_provider().add_span_processor(span_processor)
            CeleryInstrumentor().instrument()
            FlaskInstrumentor().instrument_app(app)


otel_traces = Traces()
