from functools import wraps

from flask import _request_ctx_stack, request

from opentelemetry import trace
from opentelemetry.ext import jaeger
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchExportSpanProcessor


trace.set_tracer_provider(TracerProvider())

jaeger_exporter = jaeger.JaegerSpanExporter(
    service_name="notify-api",
    agent_host_name="localhost",
    agent_port=6831,
)
span_processor = BatchExportSpanProcessor(jaeger_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)


def trace_request(f):
    @wraps(f)
    def inner(*args, **kwargs):
        tracer = trace.get_tracer(__name__)
        _request_ctx_stack.top.tracer = tracer

        with tracer.start_as_current_span(str(request.url_rule)):
            return f(*args, **kwargs)

    return inner


def span(name):
    return _request_ctx_stack.top.tracer.start_as_current_span(name)
