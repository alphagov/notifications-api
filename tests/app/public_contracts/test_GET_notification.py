from . import validate
from app.models import ApiKey, KEY_TYPE_NORMAL
from app.dao.api_key_dao import save_model_api_key
from tests import create_authorization_header


def _get(client, notification, url):
    save_model_api_key(ApiKey(
        service=notification.service,
        name='api_key',
        created_by=notification.service.created_by,
        key_type=KEY_TYPE_NORMAL
    ))
    auth_header = create_authorization_header(service_id=notification.service_id)
    return client.get(url, headers=[auth_header])


def test_get_v2_notification(client, sample_notification):
    response = _get(client, sample_notification, '/v2/notifications/{}'.format(sample_notification.id))
    validate(response.get_data(as_text=True), 'GET_notification_return_email_v2.json')


def test_get_api_sms_contract(client, sample_notification):
    response = _get(client, sample_notification, '/notifications/{}'.format(sample_notification.id))
    validate(response.get_data(as_text=True), 'GET_notification_return_sms.json')


def test_get_api_email_contract(client, sample_email_notification):
    response = _get(client, sample_email_notification, '/notifications/{}'.format(sample_email_notification.id))
    validate(response.get_data(as_text=True), 'GET_notification_return_email.json')


def test_get_job_sms_contract(client, sample_notification):
    response = _get(client, sample_notification, '/notifications/{}'.format(sample_notification.id))
    validate(response.get_data(as_text=True), 'GET_notification_return_sms.json')


def test_get_job_email_contract(client, sample_email_notification):
    response = _get(client, sample_email_notification, '/notifications/{}'.format(sample_email_notification.id))
    validate(response.get_data(as_text=True), 'GET_notification_return_email.json')


def test_get_notifications_contract(client, sample_notification, sample_email_notification):
    response = _get(client, sample_notification, '/notifications')
    validate(response.get_data(as_text=True), 'GET_notifications_return.json')
