from datetime import UTC, datetime
from unittest.mock import call

import freezegun

from app.models import ApiKeyUsage


def test_record_service_api_key_hourly_usage_at_endpoint_makes_one_record_per_hour_per_endpoint(
    sample_service,
    sample_email_template,
    sample_template_with_placeholders,
    sample_template,
    sample_api_key,
    api_client_request,
    mocker,
):

    hourly_bucket = "2026-09-15T10"
    endpoint_1 = "v2_notifications.post_notification"
    endpoint_2 = "v2_template.get_template_by_id"
    endpoint_3 = "v2_notifications.post_precompiled_letter_notification"
    redis_data = {}
    mock_redis_get = mocker.patch(
        "app.v2.api_key_usage.redis_store.get", side_effect=lambda key, skippable=False: redis_data.get(key)
    )
    mock_redis_set = mocker.patch(
        "app.v2.api_key_usage.redis_store.set",
        side_effect=lambda key, value, ex=None, skippable=False: redis_data.__setitem__(key, value.encode("utf-8")),
    )

    # endpoint_1 simulation
    for test_date in ["2026-09-15 10:05:20", "2026-09-15 10:30:35", "2026-09-15 10:45:55"]:
        with freezegun.freeze_time(test_date):
            mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
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
    for time in ["2026-09-15 10:10:20", "2026-09-15 10:20:35", "2026-09-15 10:55:55"]:
        with freezegun.freeze_time(time):
            api_client_request.get(
                sample_service.id,
                "v2_template.get_template_by_id",
                template_id=sample_template.id,
                version=None,
                _expected_status=200,
            )

    # endpoint_3 simulation
    for time in ["2026-09-15 10:15:20", "2026-09-15 10:20:35", "2026-09-15 10:55:55"]:
        with freezegun.freeze_time(time):
            mocker.patch("app.v2.notifications.post_notifications.upload_letter_pdf")
            mocker.patch("app.celery.letters_pdf_tasks.notify_celery.send_task")
            data_3 = {"reference": "letter-reference", "content": "bGV0dGVyLWNvbnRlbnQ=", "postage": "second"}

            api_client_request.post(
                sample_service.id, "v2_notifications.post_precompiled_letter_notification", _data=data_3
            )

    result = ApiKeyUsage.query.all()
    assert len(result) == 3

    assert result[0].service_id == sample_service.id
    assert result[0].api_key_id == sample_api_key.id
    assert result[0].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[0].endpoint == endpoint_1

    assert result[1].service_id == sample_service.id
    assert result[1].api_key_id == sample_api_key.id
    assert result[1].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[1].endpoint == endpoint_2

    assert result[2].service_id == sample_service.id
    assert result[2].api_key_id == sample_api_key.id
    assert result[2].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[2].endpoint == endpoint_3

    mock_api_usage_get_call_list = [
        redis_call
        for redis_call in mock_redis_get.call_args_list
        if redis_call.args[0].startswith("api-key-usage-marker")
    ]

    assert mock_api_usage_get_call_list == [
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_1}", skippable=True
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_1}", skippable=True
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_1}", skippable=True
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_2}", skippable=True
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_2}", skippable=True
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_2}", skippable=True
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_3}", skippable=True
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_3}", skippable=True
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_3}", skippable=True
        ),
    ]

    mock_api_usage_set_call_list = [
        redis_call
        for redis_call in mock_redis_set.call_args_list
        if redis_call.args[0].startswith("api-key-usage-marker")
    ]
    assert mock_api_usage_set_call_list == [
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_1}",
            "1",
            ex=10800,
            skippable=True,
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_2}",
            "1",
            ex=10800,
            skippable=True,
        ),
        call(
            f"api-key-usage-marker:{sample_service.id}:{sample_api_key.id}:{hourly_bucket}:{endpoint_3}",
            "1",
            ex=10800,
            skippable=True,
        ),
    ]


def test_record_service_api_key_hourly_usage_at_endpoint_across_different_times_in_the_day_at_same_endpoint(
    sample_template_with_placeholders,
    api_client_request,
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
            mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
            data_2 = {
                "phone_number": "07700900855",
                "template_id": str(sample_template_with_placeholders.id),
                "personalisation": {" Name": "SomeOne"},
            }
            api_client_request.post(
                sample_template_with_placeholders.service_id,
                "v2_notifications.post_notification",
                notification_type="sms",
                _data=data_2,
            )

    result = ApiKeyUsage.query.order_by(ApiKeyUsage.usage_hour.asc()).all()
    assert len(result) == 6

    assert result[0].usage_hour == datetime(2026, 9, 15, 6, 0, 0, tzinfo=UTC)
    assert result[1].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[2].usage_hour == datetime(2026, 9, 15, 13, 0, 0, tzinfo=UTC)
    assert result[3].usage_hour == datetime(2026, 9, 15, 16, 0, 0, tzinfo=UTC)
    assert result[4].usage_hour == datetime(2026, 9, 15, 20, 0, 0, tzinfo=UTC)
    assert result[5].usage_hour == datetime(2026, 9, 15, 23, 0, 0, tzinfo=UTC)

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
    assert len(mock_api_usage_get_call_list) == 11
    assert len(mock_api_usage_set_call_list) == 6
