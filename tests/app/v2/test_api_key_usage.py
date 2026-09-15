from datetime import UTC, datetime
from unittest.mock import call

import freezegun

from app.models import ApiKeyUsage
from app.v2.api_key_usage import record_service_api_key_hourly_usage_at_endpoint
from tests.app.db import create_api_key


def test_record_service_api_key_hourly_usage_at_endpoint_makes_one_record_per_hour_per_endpoint(sample_service, mocker):
    service_id = sample_service.id
    api_key = create_api_key(service=sample_service)
    api_key_id = api_key.id
    hourly_bucket = 2026091510
    endpoint_1 = "v2_notifications.post_precompiled_letter_notification"
    endpoint_2 = "v2_notifications.post_notification"
    endpoint_3 = "v2_notifications.get_templates"
    redis_data = {}
    mock_redis_get = mocker.patch(
        "app.v2.api_key_usage.redis_store.get", side_effect=lambda key, skippable=False: redis_data.get(key)
    )
    mock_redis_set = mocker.patch(
        "app.v2.api_key_usage.redis_store.set",
        side_effect=lambda key, value, ex=None, skippable=False: redis_data.__setitem__(key, value.encode("utf-8")),
    )
    # endpoint_1 simulation
    with freezegun.freeze_time("2026-09-15 10:05:20"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_1)
    with freezegun.freeze_time("2026-09-15 10:30:35"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_1)
    with freezegun.freeze_time("2026-09-15 10:45:55"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_1)

    # endpoint_2 simulation
    with freezegun.freeze_time("2026-09-15 10:10:20"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_2)
    with freezegun.freeze_time("2026-09-15 10:20:35"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_2)
    with freezegun.freeze_time("2026-09-15 10:55:55"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_2)

    # endpoint_3 simulation
    with freezegun.freeze_time("2026-09-15 10:15:20"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_3)
    with freezegun.freeze_time("2026-09-15 10:20:35"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_3)
    with freezegun.freeze_time("2026-09-15 10:55:55"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint_3)

    result = ApiKeyUsage.query.all()
    assert len(result) == 3

    assert result[0].service_id == sample_service.id
    assert result[0].api_key_id == api_key_id
    assert result[0].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[0].endpoint == endpoint_1

    assert result[1].service_id == sample_service.id
    assert result[1].api_key_id == api_key_id
    assert result[1].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[1].endpoint == endpoint_2

    assert result[2].service_id == sample_service.id
    assert result[2].api_key_id == api_key_id
    assert result[2].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[2].endpoint == endpoint_3

    assert mock_redis_get.call_args_list == [
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_1}", skippable=True),
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_1}", skippable=True),
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_1}", skippable=True),
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_2}", skippable=True),
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_2}", skippable=True),
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_2}", skippable=True),
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_3}", skippable=True),
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_3}", skippable=True),
        call(f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_3}", skippable=True),
    ]

    assert mock_redis_set.call_args_list == [
        call(
            f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_1}",
            "1",
            ex=10800,
            skippable=True,
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_2}",
            "1",
            ex=10800,
            skippable=True,
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{api_key.id}:{hourly_bucket}:{endpoint_3}",
            "1",
            ex=10800,
            skippable=True,
        ),
    ]


def test_record_service_api_key_hourly_usage_at_endpoint_across_different_times_in_the_day_at_same_endpoint(
    sample_service, mocker
):
    service_id = sample_service.id
    api_key = create_api_key(service=sample_service)
    api_key_id = api_key.id
    endpoint = "v2_notifications.post_notification"

    redis_data = {}
    mock_redis_get = mocker.patch(
        "app.v2.api_key_usage.redis_store.get", side_effect=lambda key, skippable=False: redis_data.get(key)
    )
    mock_redis_set = mocker.patch(
        "app.v2.api_key_usage.redis_store.set",
        side_effect=lambda key, value, ex=None, skippable=False: redis_data.__setitem__(key, value.encode("utf-8")),
    )

    # endpoint simulation
    with freezegun.freeze_time("2026-09-15 06:05:20"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 06:30:35"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 10:15:55"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 10:45:20"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 13:30:35"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 13:45:55"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 16:05:20"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 16:45:11"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 20:30:35"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 20:45:55"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 23:59:59"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id, service_id, endpoint)

    result = ApiKeyUsage.query.order_by(ApiKeyUsage.usage_hour.asc()).all()
    assert len(result) == 6

    assert result[0].usage_hour == datetime(2026, 9, 15, 6, 0, 0, tzinfo=UTC)
    assert result[1].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[2].usage_hour == datetime(2026, 9, 15, 13, 0, 0, tzinfo=UTC)
    assert result[3].usage_hour == datetime(2026, 9, 15, 16, 0, 0, tzinfo=UTC)
    assert result[4].usage_hour == datetime(2026, 9, 15, 20, 0, 0, tzinfo=UTC)
    assert result[5].usage_hour == datetime(2026, 9, 15, 23, 0, 0, tzinfo=UTC)

    assert mock_redis_get.call_count == 11
    assert mock_redis_set.call_count == 6


def test_record_service_api_key_hourly_usage_at_endpoint_for_different_api_keys(sample_service, mocker):
    service_id = sample_service.id
    api_key_1 = create_api_key(service=sample_service)
    api_key_id_1 = api_key_1.id
    api_key_2 = create_api_key(service=sample_service)
    api_key_id_2 = api_key_2.id
    endpoint = "v2_notifications.post_notification"

    # endpoint_1 simulation
    with freezegun.freeze_time("2026-09-15 10:30:35"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id_1, service_id, endpoint)
    with freezegun.freeze_time("2026-09-15 10:30:35"):
        record_service_api_key_hourly_usage_at_endpoint(api_key_id_2, service_id, endpoint)
