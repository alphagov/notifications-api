from flask import json

import app
from tests import create_authorization_header


def test_should_reject_if_not_authenticated(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post('/deliver/notification/{}'.format(app.create_uuid()))
            assert response.status_code == 401


def test_should_reject_if_invalid_uuid(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth = create_authorization_header()
            response = client.post(
                '/deliver/notification/{}',
                headers=[auth]
            )
        body = json.loads(response.get_data(as_text=True))
        assert response.status_code == 404
        assert body['message'] == 'The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.'  # noqa
        assert body['result'] == 'error'


def test_should_reject_if_notification_id_cannot_be_found(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth = create_authorization_header()
            response = client.post(
                '/deliver/notification/{}'.format(app.create_uuid()),
                headers=[auth]
            )
        body = json.loads(response.get_data(as_text=True))
        assert response.status_code == 404
        assert body['message'] == 'No result found'
        assert body['result'] == 'error'


def test_should_call_send_sms_to_provider_as_primary(notify_api, sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider')
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth = create_authorization_header()
            response = client.post(
                '/deliver/notification/{}'.format(sample_notification.id),
                headers=[auth]
            )
            app.delivery.send_to_providers.send_sms_to_provider.assert_called_with(sample_notification)
            assert response.status_code == 204


def test_should_call_send_email_to_provider_as_primary(notify_api, sample_email_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider')
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth = create_authorization_header()
            response = client.post(
                '/deliver/notification/{}'.format(sample_email_notification.id),
                headers=[auth]
            )
        app.delivery.send_to_providers.send_email_to_provider.assert_called_with(sample_email_notification)
        assert response.status_code == 204


def test_should_call_deliver_sms_task_if_send_sms_to_provider_fails(notify_api, sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider', side_effect=Exception())
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth = create_authorization_header()
            response = client.post(
                '/deliver/notification/{}'.format(sample_notification.id),
                headers=[auth]
            )
        app.delivery.send_to_providers.send_sms_to_provider.assert_called_with(sample_notification)
        app.celery.provider_tasks.deliver_sms.apply_async.assert_called_with(
            (str(sample_notification.id)), queue='send-sms-tasks'
        )
        assert response.status_code == 204


def test_should_call_deliver_email_task_if_send_email_to_provider_fails(
        notify_api,
        sample_email_notification,
        mocker
):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider', side_effect=Exception())
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth = create_authorization_header()
            response = client.post(
                '/deliver/notification/{}'.format(sample_email_notification.id),
                headers=[auth]
            )
        app.delivery.send_to_providers.send_email_to_provider.assert_called_with(sample_email_notification)
        app.celery.provider_tasks.deliver_email.apply_async.assert_called_with(
            (str(sample_email_notification.id)), queue='send-email-tasks'
        )
        assert response.status_code == 204
