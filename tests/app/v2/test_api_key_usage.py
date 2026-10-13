from datetime import datetime
from unittest.mock import call

import freezegun
import pytest

from app.models import ApiKeyUsage


def test_record_api_key_usage_makes_one_record_per_hour_per_endpoint(
    sample_letter_notification,
    api_client_request,
    mocker,
    sample_email_template,
    sample_service,
    sample_api_key,
):

    hourly_bucket = "2026-09-15T10"
    endpoint_1 = "v2_notifications.post_notification"
    endpoint_2 = "v2_template.post_template_preview"
    redis_data = {}
    mock_redis_get = mocker.patch(
        "app.v2.api_key_usage.redis_store.get", side_effect=lambda key, skippable=False: redis_data.get(key)
    )
    mock_redis_set = mocker.patch(
        "app.v2.api_key_usage.redis_store.set",
        side_effect=lambda key, value, ex=None, skippable=False: redis_data.__setitem__(key, value.encode("utf-8")),
    )

    # endpoint_1 simulation
    service_id_1 = sample_api_key.service_id
    api_key_id_1 = sample_api_key.id
    for test_date in ["2026-09-15 10:05:20", "2026-09-15 10:30:35", "2026-09-15 10:45:55"]:
        with freezegun.freeze_time(test_date):
            mock_provider_task = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
            data_1 = {
                "email_address": "nobody@no-one.com",
                "template_id": sample_email_template.id,
                "personalisation": {"name": "Bob"},
            }
            api_client_request.post(
                sample_service.id,
                "v2_notifications.post_notification",
                notification_type="email",
                _data=data_1,
            )

    # endpoint_2 simulation
    service_id_2 = sample_letter_notification.service_id
    api_key_id_2 = sample_letter_notification.api_key_id
    for time in ["2026-09-15 10:10:20", "2026-09-15 10:20:35", "2026-09-15 10:55:55"]:
        with freezegun.freeze_time(time):
            api_client_request.post(
                service_id_2,
                "v2_template.post_template_preview",
                template_id=sample_letter_notification.template_id,
                _data=None,
                _expected_status=200,
            )

    result = ApiKeyUsage.query.order_by(ApiKeyUsage.endpoint).all()
    assert len(result) == 2

    assert result[0].service_id == service_id_1
    assert result[0].api_key_id == api_key_id_1
    assert result[0].usage_hour == datetime(2026, 9, 15, 10, 0, 0)
    assert result[0].endpoint == endpoint_1

    assert result[1].service_id == service_id_2
    assert result[1].api_key_id == api_key_id_2
    assert result[1].usage_hour == datetime(2026, 9, 15, 10, 0, 0)
    assert result[1].endpoint == endpoint_2

    assert mock_provider_task.called is True

    mock_api_usage_get_call_list = [
        redis_call
        for redis_call in mock_redis_get.call_args_list
        if redis_call.args[0].startswith("api-key-usage-marker")
    ]

    assert mock_api_usage_get_call_list == [
        call(f"api-key-usage-marker:{service_id_1}:{api_key_id_1}:{hourly_bucket}:{endpoint_1}", skippable=True),
        call(f"api-key-usage-marker:{service_id_2}:{api_key_id_2}:{hourly_bucket}:{endpoint_2}", skippable=True),
    ]

    mock_api_usage_set_call_list = [
        redis_call
        for redis_call in mock_redis_set.call_args_list
        if redis_call.args[0].startswith("api-key-usage-marker")
    ]
    assert mock_api_usage_set_call_list == [
        call(
            f"api-key-usage-marker:{service_id_1}:{api_key_id_1}:{hourly_bucket}:{endpoint_1}",
            "1",
            ex=10800,
            skippable=True,
        ),
        call(
            f"api-key-usage-marker:{service_id_2}:{api_key_id_2}:{hourly_bucket}:{endpoint_2}",
            "1",
            ex=10800,
            skippable=True,
        ),
    ]


def test_record_api_key_usage_across_different_times_in_the_day_at_the_same_endpoint(
    sample_template_with_placeholders,
    api_client_request,
    sample_letter_notification,
    mocker,
):

    redis_data = {}
    mock_redis_get = mocker.patch(
        "app.v2.api_key_usage.redis_store.get", side_effect=lambda key, skippable=False: redis_data.get(key)
    )
    mock_redis_set = mocker.patch(
        "app.v2.api_key_usage.redis_store.set",
        side_effect=lambda key, value, ex=None, skippable=False: redis_data.__setitem__(key, value.encode("utf-8")),
    )

    service_id = sample_letter_notification.service_id

    # endpoint simulation
    for time in [
        "2026-09-15 06:05:20",
        "2026-09-15 06:30:35",
        "2026-09-15 10:15:55",
        "2026-09-15 10:45:20",
        "2026-09-15 13:30:35",
        "2026-09-15 13:45:55",
        "2026-09-15 16:05:20",
        "2026-09-15 16:45:11",
        "2026-09-15 20:30:35",
        "2026-09-15 20:45:55",
        "2026-09-15 23:59:59",
    ]:
        with freezegun.freeze_time(time):
            api_client_request.post(
                service_id,
                "v2_template.post_template_preview",
                template_id=sample_letter_notification.template_id,
                _data=None,
                _expected_status=200,
            )

    result = ApiKeyUsage.query.order_by(ApiKeyUsage.usage_hour.asc()).all()
    assert len(result) == 6

    assert result[0].usage_hour == datetime(2026, 9, 15, 6, 0, 0)
    assert result[1].usage_hour == datetime(2026, 9, 15, 10, 0, 0)
    assert result[2].usage_hour == datetime(2026, 9, 15, 13, 0, 0)
    assert result[3].usage_hour == datetime(2026, 9, 15, 16, 0, 0)
    assert result[4].usage_hour == datetime(2026, 9, 15, 20, 0, 0)
    assert result[5].usage_hour == datetime(2026, 9, 15, 23, 0, 0)

    mock_api_usage_get_call_list = [
        redis_call
        for redis_call in mock_redis_get.call_args_list
        if redis_call.args[0].startswith("api-key-usage-marker")
    ]
    mock_api_usage_set_call_list = [
        redis_call
        for redis_call in mock_redis_set.call_args_list
        if redis_call.args[0].startswith("api-key-usage-marker")
    ]
    assert len(mock_api_usage_get_call_list) == 6
    assert len(mock_api_usage_set_call_list) == 6


def test_record_api_key_doesnt_hit_redis_for_multiple_calls_from_same_instance(
    sample_letter_notification,
    api_client_request,
    client,
    mocker,
):
    redis_data = {}
    mock_redis_get = mocker.patch(
        "app.v2.api_key_usage.redis_store.get", side_effect=lambda key, skippable=False: redis_data.get(key)
    )
    mocker.patch(
        "app.v2.api_key_usage.redis_store.set",
        side_effect=lambda key, value, ex=None, skippable=False: redis_data.__setitem__(key, value.encode("utf-8")),
    )

    with freezegun.freeze_time("2026-09-15 10:10:20"):
        for _ in range(10):
            api_client_request.post(
                sample_letter_notification.service_id,
                "v2_template.post_template_preview",
                template_id=sample_letter_notification.template_id,
                _data=None,
                _expected_status=200,
            )

    assert mock_redis_get.call_args_list == [
        call(f"service-{sample_letter_notification.service_id}", skippable=True),
        call(
            (
                f"api-key-usage-marker"
                f":{sample_letter_notification.service_id}"
                f":{sample_letter_notification.api_key_id}"
                f":2026-09-15T10"
                f":v2_template.post_template_preview"
            ),
            skippable=True,
        ),
    ]


@freezegun.freeze_time("2026-09-15 10:10:20")
def test_record_api_key_doesnt_cache_if_database_write_raises_exception(
    sample_letter_notification,
    api_client_request,
    client,
    mocker,
):
    class UnexpectedError(Exception):
        pass

    mock_create_api_key_hourly_usage_record_dao = mocker.patch(
        "app.v2.api_key_usage.create_api_key_hourly_usage_record_dao",
        side_effect=UnexpectedError,
    )

    for _ in range(5):
        with pytest.raises(UnexpectedError):
            api_client_request.post(
                sample_letter_notification.service_id,
                "v2_template.post_template_preview",
                template_id=sample_letter_notification.template_id,
                _data=None,
                _expected_status=200,
            )

    assert len(mock_create_api_key_hourly_usage_record_dao.call_args_list) == 5
