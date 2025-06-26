from unittest.mock import MagicMock, patch

import pytest

from app.otel.utils import otel_histogram, otel_span, otel_span_with_status


def test_otel_span_static_attributes():
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    # Patch must be active before the decorator is applied
    with patch("app.otel.utils.get_tracer", return_value=mock_tracer):

        @otel_span(attributes={"foo": "bar"})
        def test_func(x):
            return x + 1

        result = test_func(1)
        assert result == 2
        mock_span.set_attribute.assert_any_call("foo", "bar")


def test_otel_span_dynamic_attributes():
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    with patch("app.otel.utils.get_tracer", return_value=mock_tracer):

        @otel_span(attributes=lambda args, kwargs: {"arg": args[0]})
        def test_func(x):
            return x * 2

        result = test_func(3)
        assert result == 6
        mock_span.set_attribute.assert_any_call("arg", 3)


def test_otel_span_exception_records_status():
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    with patch("app.otel.utils.get_tracer", return_value=mock_tracer):

        @otel_span()
        def test_func():
            raise ValueError("fail!")

        with pytest.raises(ValueError):
            test_func()
        mock_span.record_exception.assert_called()
        mock_span.set_status.assert_called()


def test_otel_span_with_status_success():
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    with otel_span_with_status(mock_tracer, "test-span", foo="bar") as span:
        assert span is mock_span
    mock_span.set_attribute.assert_any_call("foo", "bar")
    mock_span.set_status.assert_not_called()


def test_otel_span_with_status_exception():
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    with pytest.raises(RuntimeError):
        with otel_span_with_status(mock_tracer, "test-span", foo="bar"):
            raise RuntimeError("fail!")
    mock_span.record_exception.assert_called()
    mock_span.set_status.assert_called()


def test_otel_histogram_records_success():
    mock_meter = MagicMock()
    mock_histogram = MagicMock()
    mock_meter.create_histogram.return_value = mock_histogram

    with patch("app.otel.utils.get_meter", return_value=mock_meter):

        @otel_histogram("test_histogram", attributes={"foo": "bar"})
        def test_func(x):
            return x + 1

        result = test_func(2)
        assert result == 3
        # Should record with status "success"
        mock_histogram.record.assert_called()
        args, kwargs = mock_histogram.record.call_args
        assert kwargs["attributes"]["foo"] == "bar"
        assert kwargs["attributes"]["status"] == "success"


def test_otel_histogram_records_error():
    mock_meter = MagicMock()
    mock_histogram = MagicMock()
    mock_meter.create_histogram.return_value = mock_histogram

    with patch("app.otel.utils.get_meter", return_value=mock_meter):

        @otel_histogram("test_histogram")
        def test_func():
            raise RuntimeError("fail!")

        with pytest.raises(RuntimeError):
            test_func()
        # Should record with status "error"
        mock_histogram.record.assert_called()
        _, kwargs = mock_histogram.record.call_args
        assert kwargs["attributes"]["status"] == "error"


def test_otel_histogram_dynamic_attributes():
    mock_meter = MagicMock()
    mock_histogram = MagicMock()
    mock_meter.create_histogram.return_value = mock_histogram

    with patch("app.otel.utils.get_meter", return_value=mock_meter):

        @otel_histogram("test_histogram", attributes=lambda args, kwargs: {"arg": args[0]})
        def test_func(x):
            return x * 2

        test_func(5)
        mock_histogram.record.assert_called()
        _, kwargs = mock_histogram.record.call_args
        assert kwargs["attributes"]["arg"] == 5
        assert kwargs["attributes"]["status"] == "success"
