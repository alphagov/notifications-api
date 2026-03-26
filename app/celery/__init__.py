from opentelemetry.metrics import get_meter

notification_deliver_duration_histogram = get_meter(__name__).create_histogram(
    "notification.deliver.duration",
    unit="s",
    description="Elapsed time between sending a notification to a provider and receiving a callback from that provider.",  # noqa: E501
    # Buckets ranging from 1 second to 30 hours
    explicit_bucket_boundaries_advisory=[
        1,
        2,
        4,
        8,
        15,
        30,
        60,
        120,
        240,
        480,
        900,
        1800,
        3600,
        7200,
        14400,
        28800,
        54000,
        108000,
    ],
)
