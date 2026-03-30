from notifications_utils.semconv import HTTP_DURATION_HISTOGRAM_BUCKETS
from opentelemetry.metrics import get_meter

provider_request_duration_histogram = get_meter(__name__).create_histogram(
    "provider.request.duration",
    unit="s",
    description="The total time taken to make a request to a provider.",
    explicit_bucket_boundaries_advisory=HTTP_DURATION_HISTOGRAM_BUCKETS,
)
