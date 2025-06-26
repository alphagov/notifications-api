from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.otel import init_otel_app


@pytest.fixture
def app():
    app = Flask(__name__)
    app.logger = MagicMock()
    app.config = {}
    return app


@pytest.fixture
def otel_patches():
    """Fixture to patch all otel dependencies and yield the mocks as a dict."""
    patchers = {
        "instrument_app": patch("app.otel._instrument_app"),
        "batch_span_processor": patch("app.otel.BatchSpanProcessor"),
        "console_span_exporter": patch("app.otel.ConsoleSpanExporter"),
        "periodic_exporting_metric_reader": patch("app.otel.PeriodicExportingMetricReader"),
        "console_metric_exporter": patch("app.otel.ConsoleMetricExporter"),
        "meter_provider": patch("app.otel.MeterProvider"),
        "metrics": patch("app.otel.metrics"),
        "tracer_provider": patch("app.otel.TracerProvider"),
        "set_tracer_provider": patch("app.otel.set_tracer_provider"),
        "get_tracer_provider": patch("app.otel.get_tracer_provider"),
        "baggage_span_processor": patch("app.otel.BaggageSpanProcessor"),
        "allow_all_baggage_keys": patch("app.otel.ALLOW_ALL_BAGGAGE_KEYS"),
        "resource": patch("app.otel.Resource"),
        "otlp_span_exporter": patch("app.otel.OTLPSpanExporter"),
        "otlp_metric_exporter": patch("app.otel.OTLPMetricExporter"),
    }
    mocks = {}
    started = []
    for name, patcher in patchers.items():
        started.append(patcher.start())
        mocks[name] = started[-1]
    try:
        yield mocks
    finally:
        for patcher in patchers.values():
            patcher.stop()


def test_already_instrumented(otel_patches, app):
    app._otel_instrumented = True
    init_otel_app(app)
    app.logger.debug.assert_called_once_with("OpenTelemetry instrumentation already applied, skipping.")
    otel_patches["instrument_app"].assert_not_called()


def test_console_export(otel_patches, app):
    app.config = {"OTEL_EXPORT_TYPE": "console"}
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    app.logger.info.assert_any_call("OpenTelemetry metrics and spans will be exported to console")
    otel_patches["metrics"].set_meter_provider.assert_called_once()
    otel_patches["set_tracer_provider"].assert_called_once()
    otel_patches["get_tracer_provider"].return_value.add_span_processor.assert_any_call(
        otel_patches["baggage_span_processor"]()
    )
    otel_patches["get_tracer_provider"].return_value.add_span_processor.assert_any_call(
        otel_patches["batch_span_processor"]()
    )
    otel_patches["instrument_app"].assert_called_once_with(app)
    assert app._otel_instrumented is True


def test_otlp_export(otel_patches, app):
    app.config = {
        "OTEL_EXPORT_TYPE": "otlp",
        "OTEL_COLLECTOR_ENDPOINT": "test-endpoint:4317",
        "OTEL_COLLECTOR_INSECURE": False,
    }
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    app.logger.info.assert_any_call(
        "OpenTelemetry metrics and spans will be exported to OTLP collector at %s", "test-endpoint:4317"
    )
    otel_patches["metrics"].set_meter_provider.assert_called_once()
    otel_patches["set_tracer_provider"].assert_called_once()
    otel_patches["get_tracer_provider"].return_value.add_span_processor.assert_any_call(
        otel_patches["baggage_span_processor"]()
    )
    otel_patches["get_tracer_provider"].return_value.add_span_processor.assert_any_call(
        otel_patches["batch_span_processor"]()
    )
    otel_patches["instrument_app"].assert_called_once_with(app)
    assert app._otel_instrumented is True


def test_none_export(otel_patches, app):
    app.config = {"OTEL_EXPORT_TYPE": "none"}
    init_otel_app(app)
    app.logger.info.assert_any_call("OpenTelemetry metrics and spans will not be exported")
    otel_patches["instrument_app"].assert_not_called()
    assert not hasattr(app, "_otel_instrumented") or not app._otel_instrumented


def test_invalid_export_type(otel_patches, app):
    app.config = {"OTEL_EXPORT_TYPE": "invalid"}
    with pytest.raises(ValueError, match="Invalid OTEL_EXPORT_TYPE: invalid. Expected 'console', 'otlp', or 'none'."):
        init_otel_app(app)


def test_default_export_type_is_none(otel_patches, app):
    # If OTEL_EXPORT_TYPE is not set, should behave as 'none'
    init_otel_app(app)
    app.logger.info.assert_any_call("OpenTelemetry metrics and spans will not be exported")
    otel_patches["instrument_app"].assert_not_called()
    assert not hasattr(app, "_otel_instrumented") or not app._otel_instrumented


def test_instrumentation_sets_flag(otel_patches, app):
    app.config = {"OTEL_EXPORT_TYPE": "console"}
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    assert app._otel_instrumented is True


def test_logger_debug_called_when_already_instrumented(otel_patches, app):
    app._otel_instrumented = True
    init_otel_app(app)
    app.logger.debug.assert_called_once_with("OpenTelemetry instrumentation already applied, skipping.")
    otel_patches["instrument_app"].assert_not_called()


def test_otlp_export_insecure_true(otel_patches, app):
    app.config = {
        "OTEL_EXPORT_TYPE": "otlp",
        "OTEL_COLLECTOR_ENDPOINT": "test-endpoint:4317",
        "OTEL_COLLECTOR_INSECURE": True,
    }
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    app.logger.info.assert_any_call(
        "OpenTelemetry metrics and spans will be exported to OTLP collector at %s", "test-endpoint:4317"
    )
    otel_patches["metrics"].set_meter_provider.assert_called_once()
    otel_patches["set_tracer_provider"].assert_called_once()
    otel_patches["get_tracer_provider"].return_value.add_span_processor.assert_any_call(
        otel_patches["baggage_span_processor"]()
    )
    otel_patches["get_tracer_provider"].return_value.add_span_processor.assert_any_call(
        otel_patches["batch_span_processor"]()
    )
    otel_patches["instrument_app"].assert_called_once_with(app)
    assert app._otel_instrumented is True


def test_export_type_case_insensitive(otel_patches, app):
    app.config = {"OTEL_EXPORT_TYPE": "Console"}
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    app.logger.info.assert_any_call("OpenTelemetry metrics and spans will be exported to console")
    otel_patches["instrument_app"].assert_called_once_with(app)
    assert app._otel_instrumented is True


def test_export_type_missing_logger(otel_patches, app):
    class DummyApp:
        config = {"OTEL_EXPORT_TYPE": "none"}

        logger = MagicMock()

    dummy_app = DummyApp()
    # Should not raise even if logger is missing
    init_otel_app(dummy_app)
    otel_patches["instrument_app"].assert_not_called()

    # Now test with a real app and otel_patches
    app.config = {"OTEL_EXPORT_TYPE": "console"}
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    app.logger.info.assert_any_call("OpenTelemetry metrics and spans will be exported to console")
    otel_patches["metrics"].set_meter_provider.assert_called_once()
    otel_patches["set_tracer_provider"].assert_called_once()
    otel_patches["get_tracer_provider"].return_value.add_span_processor.assert_any_call(
        otel_patches["baggage_span_processor"]()
    )
    otel_patches["get_tracer_provider"].return_value.add_span_processor.assert_any_call(
        otel_patches["batch_span_processor"]()
    )
    otel_patches["instrument_app"].assert_called_once_with(app)
    assert app._otel_instrumented is True


def test_multiple_calls_are_idempotent(otel_patches, app):
    """Calling init_otel_app twice should not re-instrument."""
    app.config = {"OTEL_EXPORT_TYPE": "console"}
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    otel_patches["instrument_app"].assert_called_once_with(app)
    otel_patches["instrument_app"].reset_mock()
    init_otel_app(app)
    otel_patches["instrument_app"].assert_not_called()
    app.logger.debug.assert_called_with("OpenTelemetry instrumentation already applied, skipping.")


def test_otlp_export_missing_insecure_defaults_false(otel_patches, app):
    """If OTEL_COLLECTOR_INSECURE is missing, should default to False."""
    app.config = {
        "OTEL_EXPORT_TYPE": "otlp",
        "OTEL_COLLECTOR_ENDPOINT": "test-endpoint:4317",
        # OTEL_COLLECTOR_INSECURE not set
    }
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    app.logger.info.assert_any_call(
        "OpenTelemetry metrics and spans will be exported to OTLP collector at %s", "test-endpoint:4317"
    )
    otel_patches["instrument_app"].assert_called_once_with(app)
    assert app._otel_instrumented is True


def test_export_type_with_whitespace(otel_patches, app):
    """Handles export type with leading/trailing whitespace."""
    app.config = {"OTEL_EXPORT_TYPE": "  console  "}
    otel_patches["get_tracer_provider"].return_value = MagicMock()
    init_otel_app(app)
    app.logger.info.assert_any_call("OpenTelemetry metrics and spans will be exported to console")
    otel_patches["instrument_app"].assert_called_once_with(app)
    assert app._otel_instrumented is True
