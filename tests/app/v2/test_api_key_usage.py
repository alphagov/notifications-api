from datetime import UTC, datetime
from unittest.mock import call

import freezegun
from flask import url_for

from app.models import ApiKeyUsage
from tests import create_service_authorization_header


def test_record_api_key_usage_makes_one_record_per_hour_per_endpoint(
    sample_service,
    sample_letter_notification,
    sample_template,
    sample_api_key,
    api_client_request,
    client,
    mocker,
):

    hourly_bucket = "2026-09-15T10"
    endpoint_1 = "v2_notifications.get_pdf_for_notification"
    endpoint_2 = "v2_template.post_template_preview"
    redis_data = {}
    mock_redis_get = mocker.patch(
        "app.v2.api_key_usage.redis_store.get", side_effect=lambda key, skippable=False: redis_data.get(key)
    )
    mock_redis_set = mocker.patch(
        "app.v2.api_key_usage.redis_store.set",
        side_effect=lambda key, value, ex=None, skippable=False: redis_data.__setitem__(key, value.encode("utf-8")),
    )

    service_id = sample_letter_notification.service_id
    api_key_id = sample_letter_notification.api_key_id

    # endpoint_1 simulation
    for test_date in ["2026-09-15 10:05:20", "2026-09-15 10:30:35", "2026-09-15 10:45:55"]:
        with freezegun.freeze_time(test_date):
            mocker.patch(
                "app.v2.notifications.get_notifications.get_letter_pdf_and_metadata",
                return_value=(b"foo", {"message": "", "invalid_pages": "", "page_count": "1"}),
            )
            sample_letter_notification.status = "created"

            auth_header = create_service_authorization_header(service_id=service_id)
            client.get(
                path=url_for(
                    "v2_notifications.get_pdf_for_notification", notification_id=sample_letter_notification.id
                ),
                headers=[("Content-Type", "application/json"), auth_header],
            )

    # endpoint_2 simulation
    for time in ["2026-09-15 10:10:20", "2026-09-15 10:20:35", "2026-09-15 10:55:55"]:
        with freezegun.freeze_time(time):
            api_client_request.post(
                service_id,
                "v2_template.post_template_preview",
                template_id=sample_letter_notification.template_id,
                _data=None,
                _expected_status=200,
            )

    result = ApiKeyUsage.query.all()
    assert len(result) == 2

    assert result[0].service_id == service_id
    assert result[0].api_key_id == api_key_id
    assert result[0].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[0].endpoint == endpoint_1

    assert result[1].service_id == service_id
    assert result[1].api_key_id == api_key_id
    assert result[1].usage_hour == datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    assert result[1].endpoint == endpoint_2

    mock_api_usage_get_call_list = [
        redis_call
        for redis_call in mock_redis_get.call_args_list
        if redis_call.args[0].startswith("api-key-usage-marker")
    ]

    assert mock_api_usage_get_call_list == [
        call(f"api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint_1}", skippable=True),
        call(f"api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint_1}", skippable=True),
        call(f"api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint_1}", skippable=True),
        call(f"api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint_2}", skippable=True),
        call(f"api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint_2}", skippable=True),
        call(f"api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint_2}", skippable=True),
    ]

    mock_api_usage_set_call_list = [
        redis_call
        for redis_call in mock_redis_set.call_args_list
        if redis_call.args[0].startswith("api-key-usage-marker")
    ]
    assert mock_api_usage_set_call_list == [
        call(
            f"api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint_1}",
            "1",
            ex=10800,
            skippable=True,
        ),
        call(
            f"api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint_2}",
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
