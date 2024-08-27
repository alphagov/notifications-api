from app.constants import KEY_TYPE_NORMAL
from app.dao.api_key_dao import save_model_api_key
from app.models import ApiKey
from app.v2.notifications.notification_schemas import (
    get_notification_response,
    get_notifications_response,
)
from tests import create_service_authorization_header

from . import return_json_from_response, validate


def _get_notification(client, notification, url):
    save_model_api_key(
        ApiKey(
            service=notification.service,
            name="api_key",
            created_by=notification.service.created_by,
            key_type=KEY_TYPE_NORMAL,
        )
    )
    auth_header = create_service_authorization_header(service_id=notification.service_id)
    return client.get(url, headers=[auth_header])


# v2


def test_get_v2_sms_contract(client, sample_notification, sms_rate):
    response_json = return_json_from_response(
        _get_notification(client, sample_notification, f"/v2/notifications/{sample_notification.id}")
    )
    validate(response_json, get_notification_response)


def test_get_v2_email_contract(client, sample_email_notification):
    response_json = return_json_from_response(
        _get_notification(client, sample_email_notification, f"/v2/notifications/{sample_email_notification.id}")
    )
    validate(response_json, get_notification_response)


def test_get_v2_notifications_contract(client, sample_notification, sms_rate):
    response_json = return_json_from_response(_get_notification(client, sample_notification, "/v2/notifications"))
    validate(response_json, get_notifications_response)
