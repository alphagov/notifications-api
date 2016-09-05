from . import validate
from app.models import ApiKey, KEY_TYPE_NORMAL
from app.dao.notifications_dao import dao_update_notification
from app.dao.api_key_dao import save_model_api_key
from tests import create_authorization_header


def test_get_api_sms_contract(client, sample_notification):
    api_key = ApiKey(service=sample_notification.service,
                     name='api_key',
                     created_by=sample_notification.service.created_by,
                     key_type=KEY_TYPE_NORMAL)
    save_model_api_key(api_key)
    sample_notification.job = None
    sample_notification.api_key = api_key
    sample_notification.key_type = KEY_TYPE_NORMAL
    dao_update_notification(sample_notification)
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get('/notifications/{}'.format(sample_notification.id), headers=[auth_header])

    validate(response.get_data(as_text=True), 'GET_notification_return_sms.json')


def test_get_api_email_contract(client, sample_email_notification):
    api_key = ApiKey(service=sample_email_notification.service,
                     name='api_key',
                     created_by=sample_email_notification.service.created_by,
                     key_type=KEY_TYPE_NORMAL)
    save_model_api_key(api_key)
    sample_email_notification.job = None
    sample_email_notification.api_key = api_key
    sample_email_notification.key_type = KEY_TYPE_NORMAL
    dao_update_notification(sample_email_notification)

    auth_header = create_authorization_header(service_id=sample_email_notification.service_id)
    response = client.get('/notifications/{}'.format(sample_email_notification.id), headers=[auth_header])

    validate(response.get_data(as_text=True), 'GET_notification_return_email.json')


def test_get_job_sms_contract(client, sample_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get('/notifications/{}'.format(sample_notification.id), headers=[auth_header])

    validate(response.get_data(as_text=True), 'GET_notification_return_sms.json')


def test_get_job_email_contract(client, sample_email_notification):
    auth_header = create_authorization_header(service_id=sample_email_notification.service_id)
    response = client.get('/notifications/{}'.format(sample_email_notification.id), headers=[auth_header])

    validate(response.get_data(as_text=True), 'GET_notification_return_email.json')


def test_get_notifications_contract(client, sample_notification, sample_email_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get('/notifications', headers=[auth_header])

    validate(response.get_data(as_text=True), 'GET_notifications_return.json')
