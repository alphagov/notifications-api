from datetime import UTC, datetime

from flask import request
from notifications_utils.clients.redis import RequestCache

from app import api_user, authenticated_service, redis_store
from app.dao.api_key_dao import create_api_key_hourly_usage_record_dao

redis_cache = RequestCache(redis_store)


def record_api_key_hourly_usage():
    """
    This function records api key usage at an endpoint.
    Only one entry will be made in the api_key_usage for an api key at an endpoint each hour.
    Whenever an entry is made in the database for api key usage at an endpoint, a cache key is set as a marker for
    that entry. The existence of the marker prevents recording any further uses of the api key at that
    endpoint for that hour ie from 10:00:00 to 10:59:59.
    """
    service_id = authenticated_service.id
    api_key_id = api_user.id
    usage_hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    endpoint = request.endpoint
    # hourly_bucket is of the format "%Y%m%d%T%H", ie the hourly_bucket for 10:00:00 to 10:59:59 UTC on 08/09/2026
    # would be 20260908T10
    hourly_bucket = usage_hour.strftime("%Y-%m-%dT%H")

    _record_service_api_key_hourly_usage(api_key_id, service_id, hourly_bucket, endpoint, usage_hour)


@redis_cache.set("api-key-usage-marker:{service_id}:{api_key_id}:{hourly_bucket}:{endpoint}", ttl_in_seconds=10800)
def _record_service_api_key_hourly_usage(api_key_id, service_id, hourly_bucket, endpoint, usage_hour):
    # create record in the database
    create_api_key_hourly_usage_record_dao(
        service_id=service_id, api_key_id=api_key_id, endpoint=endpoint, usage_hour=usage_hour
    )
    return 1
