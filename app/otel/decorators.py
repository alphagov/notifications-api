import functools
import time

from app.otel.metrics import otel_metrics


def otel(counter_name=None, histogram_name=None, attributes=None):
    if attributes is None:
        attributes = {}

    def time_function(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.monotonic()
            c_name = counter_name or func.__name__
            h_name = histogram_name or f"{func.__name__}_time"

            # Create counter if it doesn't exist
            if not hasattr(otel_metrics, c_name):
                setattr(
                    otel_metrics,
                    c_name,
                    otel_metrics.meter.create_counter(c_name, description=f"Calls to the {func.__name__} task"),
                )
            counter = getattr(otel_metrics, c_name)

            # Create histogram if it doesn't exist
            if not hasattr(otel_metrics, h_name):
                setattr(
                    otel_metrics,
                    h_name,
                    otel_metrics.meter.create_histogram(
                        h_name,
                        description=f"time taken to execute {func.__name__} function",
                        explicit_bucket_boundaries_advisory=getattr(otel_metrics, "default_histogram_bucket", None),
                    ),
                )
            histogram = getattr(otel_metrics, h_name)

            try:
                result = func(*args, **kwargs)
                elapsed_time = time.monotonic() - start_time

                counter.add(
                    amount=1,
                    attributes={**attributes, "function_name": func.__name__, "status": "success"},
                )

                histogram.record(
                    amount=elapsed_time,
                    attributes={**attributes, "function_name": func.__name__, "status": "success"},
                )

            except Exception as e:
                elapsed_time = time.monotonic() - start_time
                counter.add(
                    amount=1,
                    attributes={**attributes, "function_name": func.__name__, "status": "error"},
                )
                histogram.record(
                    amount=elapsed_time,
                    attributes={**attributes, "function_name": func.__name__, "status": "error"},
                )
                raise e
            else:
                return result

        return wrapper

    return time_function
