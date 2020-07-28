import random
import string
import pytest

from flask import (json, current_app)
from freezegun import freeze_time
from notifications_python_client.authentication import create_jwt_token
from notifications_utils import SMS_CHAR_COUNT_LIMIT

import app
from app.dao import notifications_dao
from app.models import (
    SMS_TYPE, EMAIL_TYPE,
    ApiKey, KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST, Notification, NotificationHistory
)
from app.dao.templates_dao import dao_get_all_templates_for_service, dao_update_template
from app.dao.services_dao import dao_update_service
from app.dao.api_key_dao import save_model_api_key
from app.errors import InvalidRequest
from app.models import Template
from app.v2.errors import RateLimitError

from tests import create_authorization_header
from tests.app.db import (
    create_api_key,
    create_notification,
    create_service,
    create_service_whitelist,
    create_template,
    create_reply_to_email,
)


@pytest.mark.parametrize('template_type',
                         [SMS_TYPE, EMAIL_TYPE])
def test_create_notification_should_reject_if_missing_required_fields(notify_api,
                                                                      sample_api_key, mocker, template_type):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(template_type))
            data = {}
            auth_header = create_authorization_header(service_id=sample_api_key.service_id)

            response = client.post(
                path='/notifications/{}'.format(template_type),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['to'][0]
            assert 'Missing data for required field.' in json_resp['message']['template'][0]
            assert response.status_code == 400


def test_should_reject_bad_phone_numbers(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

            data = {
                'to': 'invalid',
                'template': sample_template.id
            }
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()
            assert json_resp['result'] == 'error'
            assert len(json_resp['message'].keys()) == 1
            assert 'Invalid phone number: Must not contain letters or symbols' in json_resp['message']['to']
            assert response.status_code == 400


@pytest.mark.parametrize('template_type, to',
                         [(SMS_TYPE, '+447700900855'),
                          (EMAIL_TYPE, 'ok@ok.com')])
def test_send_notification_invalid_template_id(notify_api, sample_template, mocker, fake_uuid, template_type, to):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(template_type))

            data = {
                'to': to,
                'template': fake_uuid
            }
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/{}'.format(template_type),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()
            assert response.status_code == 400
            test_string = 'Template not found'
            assert test_string in json_resp['message']


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_notification_with_placeholders_replaced(notify_api, sample_email_template_with_placeholders, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

            data = {
                'to': 'ok@ok.com',
                'template': str(sample_email_template_with_placeholders.id),
                'personalisation': {
                    'name': 'Jo'
                }
            }
            auth_header = create_authorization_header(service_id=sample_email_template_with_placeholders.service.id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            response_data = json.loads(response.data)['data']
            notification_id = response_data['notification']['id']
            data.update({"template_version": sample_email_template_with_placeholders.version})

            mocked.assert_called_once_with(
                [notification_id],
                queue="send-email-tasks"
            )
            assert response.status_code == 201
            assert response_data['body'] == u'Hello Jo\nThis is an email from GOV.UK'
            assert response_data['subject'] == 'Jo'


@pytest.mark.parametrize('personalisation, expected_body, expected_subject', [
    (
        ['Jo', 'John', 'Josephine'],
        (
            'Hello \n\n'
            '* Jo\n'
            '* John\n'
            '* Josephine\n'
            'This is an email from GOV.UK'
        ),
        'Jo, John and Josephine',
    ),
    (
        6,
        (
            'Hello 6\n'
            'This is an email from GOV.UK'
        ),
        '6',
    ),
    pytest.param(
        None,
        ('we consider None equivalent to missing personalisation'),
        '',
        marks=pytest.mark.xfail
    ),
])
def test_send_notification_with_placeholders_replaced_with_unusual_types(
    client,
    sample_email_template_with_placeholders,
    mocker,
    personalisation,
    expected_body,
    expected_subject,
):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    response = client.post(
        path='/notifications/email',
        data=json.dumps(
            {
                'to': 'ok@ok.com',
                'template': str(sample_email_template_with_placeholders.id),
                'personalisation': {
                    'name': personalisation
                }
            }
        ),
        headers=[
            ('Content-Type', 'application/json'),
            create_authorization_header(service_id=sample_email_template_with_placeholders.service.id)
        ]
    )

    assert response.status_code == 201
    response_data = json.loads(response.data)['data']
    assert response_data['body'] == expected_body
    assert response_data['subject'] == expected_subject


def test_should_not_send_notification_for_archived_template(notify_api, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            sample_template.archived = True
            dao_update_template(sample_template)
            json_data = json.dumps({
                'to': '+447700900855',
                'template': sample_template.id
            })
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            resp = client.post(
                path='/notifications/sms',
                data=json_data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert 'Template has been deleted' in json_resp['message']


@pytest.mark.parametrize('template_type, to',
                         [(SMS_TYPE, '+447700900855'),
                          (EMAIL_TYPE, 'not-someone-we-trust@email-address.com')])
def test_should_not_send_notification_if_restricted_and_not_a_service_user(notify_api,
                                                                           sample_template,
                                                                           sample_email_template,
                                                                           mocker,
                                                                           template_type,
                                                                           to):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(template_type))
            template = sample_template if template_type == SMS_TYPE else sample_email_template
            template.service.restricted = True
            dao_update_service(template.service)
            data = {
                'to': to,
                'template': template.id
            }

            auth_header = create_authorization_header(service_id=template.service_id)

            response = client.post(
                path='/notifications/{}'.format(template_type),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()

            assert response.status_code == 400
            assert [(
                'Can’t send to this recipient when service is in trial mode '
                '– see https://www.notifications.service.gov.uk/trial-mode'
            )] == json_resp['message']['to']


@pytest.mark.parametrize('template_type',
                         [SMS_TYPE, EMAIL_TYPE])
def test_should_send_notification_if_restricted_and_a_service_user(notify_api,
                                                                   sample_template,
                                                                   sample_email_template,
                                                                   template_type,
                                                                   mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(template_type))

            template = sample_template if template_type == SMS_TYPE else sample_email_template
            to = template.service.created_by.mobile_number if template_type == SMS_TYPE \
                else template.service.created_by.email_address
            template.service.restricted = True
            dao_update_service(template.service)
            data = {
                'to': to,
                'template': template.id
            }

            auth_header = create_authorization_header(service_id=template.service_id)

            response = client.post(
                path='/notifications/{}'.format(template_type),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert mocked.called == 1
            assert response.status_code == 201


@pytest.mark.parametrize('template_type',
                         [SMS_TYPE, EMAIL_TYPE])
def test_should_not_allow_template_from_another_service(notify_api,
                                                        service_factory,
                                                        sample_user,
                                                        mocker,
                                                        template_type):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(template_type))
            service_1 = service_factory.get('service 1', user=sample_user, email_from='service.1')
            service_2 = service_factory.get('service 2', user=sample_user, email_from='service.2')

            service_2_templates = dao_get_all_templates_for_service(service_id=service_2.id)
            to = sample_user.mobile_number if template_type == SMS_TYPE else sample_user.email_address
            data = {
                'to': to,
                'template': service_2_templates[0].id
            }

            auth_header = create_authorization_header(service_id=service_1.id)

            response = client.post(
                path='/notifications/{}'.format(template_type),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()
            assert response.status_code == 400
            test_string = 'Template not found'
            assert test_string in json_resp['message']


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_allow_valid_sms_notification(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

            data = {
                'to': '07700 900 855',
                'template': str(sample_template.id)
            }

            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            response_data = json.loads(response.data)['data']
            notification_id = response_data['notification']['id']

            mocked.assert_called_once_with([notification_id], queue='send-sms-tasks')
            assert response.status_code == 201
            assert notification_id
            assert 'subject' not in response_data
            assert response_data['body'] == sample_template.content
            assert response_data['template_version'] == sample_template.version


def test_should_reject_email_notification_with_bad_email(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
            to_address = "bad-email"
            data = {
                'to': to_address,
                'template': str(sample_email_template.service_id)
            }
            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            data = json.loads(response.get_data(as_text=True))
            mocked.apply_async.assert_not_called()
            assert response.status_code == 400
            assert data['result'] == 'error'
            assert data['message']['to'][0] == 'Not a valid email address'


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_allow_valid_email_notification(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

            data = {
                'to': 'ok@ok.com',
                'template': str(sample_email_template.id)
            }

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 201
            response_data = json.loads(response.get_data(as_text=True))['data']
            notification_id = response_data['notification']['id']
            app.celery.provider_tasks.deliver_email.apply_async.assert_called_once_with(
                [notification_id],
                queue="send-email-tasks"
            )

            assert response.status_code == 201
            assert notification_id
            assert response_data['subject'] == 'Email Subject'
            assert response_data['body'] == sample_email_template.content
            assert response_data['template_version'] == sample_email_template.version


@pytest.mark.parametrize('restricted', [True, False])
@freeze_time("2016-01-01 12:00:00.061258")
def test_should_allow_api_call_if_under_day_limit_regardless_of_type(
        notify_api,
        sample_user,
        mocker,
        restricted):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

            service = create_service(restricted=restricted, message_limit=2)
            email_template = create_template(service, template_type=EMAIL_TYPE)
            sms_template = create_template(service, template_type=SMS_TYPE)
            create_notification(template=email_template)

            data = {
                'to': sample_user.mobile_number,
                'template': str(sms_template.id)
            }

            auth_header = create_authorization_header(service_id=service.id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201


def test_should_not_return_html_in_body(notify_api, sample_service, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
            email_template = create_template(sample_service, template_type=EMAIL_TYPE, content='hello\nthere')

            data = {
                'to': 'ok@ok.com',
                'template': str(email_template.id)
            }

            auth_header = create_authorization_header(service_id=email_template.service_id)
            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201
            assert json.loads(response.get_data(as_text=True))['data']['body'] == 'hello\nthere'


def test_should_not_send_email_if_team_api_key_and_not_a_service_user(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
        data = {
            'to': "not-someone-we-trust@email-address.com",
            'template': str(sample_email_template.id),
        }

        auth_header = create_authorization_header(service_id=sample_email_template.service_id, key_type=KEY_TYPE_TEAM)

        response = client.post(
            path='/notifications/email',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), auth_header])

        json_resp = json.loads(response.get_data(as_text=True))

        app.celery.provider_tasks.deliver_email.apply_async.assert_not_called()

        assert response.status_code == 400
        assert [
            'Can’t send to this recipient using a team-only API key'
        ] == json_resp['message']['to']


def test_should_not_send_sms_if_team_api_key_and_not_a_service_user(notify_api, sample_template, mocker):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

        data = {
            'to': '07123123123',
            'template': str(sample_template.id),
        }

        auth_header = create_authorization_header(service_id=sample_template.service_id, key_type=KEY_TYPE_TEAM)

        response = client.post(
            path='/notifications/sms',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), auth_header])

        json_resp = json.loads(response.get_data(as_text=True))
        app.celery.provider_tasks.deliver_sms.apply_async.assert_not_called()

        assert response.status_code == 400
        assert [
            'Can’t send to this recipient using a team-only API key'
        ] == json_resp['message']['to']


def test_should_send_email_if_team_api_key_and_a_service_user(client, sample_email_template, fake_uuid, mocker):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    mocker.patch('app.notifications.process_notifications.uuid.uuid4', return_value=fake_uuid)

    data = {
        'to': sample_email_template.service.created_by.email_address,
        'template': sample_email_template.id
    }
    auth_header = create_authorization_header(service_id=sample_email_template.service_id, key_type=KEY_TYPE_TEAM)

    response = client.post(
        path='/notifications/email',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    app.celery.provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [fake_uuid],
        queue='send-email-tasks'
    )
    assert response.status_code == 201


@pytest.mark.parametrize('restricted', [True, False])
@pytest.mark.parametrize('limit', [0, 1])
def test_should_send_sms_to_anyone_with_test_key(
    client, sample_template, mocker, restricted, limit, fake_uuid
):
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    mocker.patch('app.notifications.process_notifications.uuid.uuid4', return_value=fake_uuid)

    data = {
        'to': '07811111111',
        'template': sample_template.id
    }
    sample_template.service.restricted = restricted
    sample_template.service.message_limit = limit
    api_key = ApiKey(
        service=sample_template.service,
        name='test_key',
        created_by=sample_template.created_by,
        key_type=KEY_TYPE_TEST
    )
    save_model_api_key(api_key)
    auth_header = create_jwt_token(secret=api_key.secret, client_id=str(api_key.service_id))

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))]
    )
    app.celery.provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [fake_uuid], queue='research-mode-tasks'
    )
    assert response.status_code == 201


@pytest.mark.parametrize('restricted', [True, False])
@pytest.mark.parametrize('limit', [0, 1])
def test_should_send_email_to_anyone_with_test_key(
    client, sample_email_template, mocker, restricted, limit, fake_uuid
):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    mocker.patch('app.notifications.process_notifications.uuid.uuid4', return_value=fake_uuid)

    data = {
        'to': 'anyone123@example.com',
        'template': sample_email_template.id
    }
    sample_email_template.service.restricted = restricted
    sample_email_template.service.message_limit = limit
    api_key = ApiKey(
        service=sample_email_template.service,
        name='test_key',
        created_by=sample_email_template.created_by,
        key_type=KEY_TYPE_TEST
    )
    save_model_api_key(api_key)
    auth_header = create_jwt_token(secret=api_key.secret, client_id=str(api_key.service_id))

    response = client.post(
        path='/notifications/email',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))]
    )

    app.celery.provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [fake_uuid], queue='research-mode-tasks'
    )
    assert response.status_code == 201


def test_should_send_sms_if_team_api_key_and_a_service_user(client, sample_template, fake_uuid, mocker):
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    mocker.patch('app.notifications.process_notifications.uuid.uuid4', return_value=fake_uuid)

    data = {
        'to': sample_template.service.created_by.mobile_number,
        'template': sample_template.id
    }
    api_key = ApiKey(service=sample_template.service,
                     name='team_key',
                     created_by=sample_template.created_by,
                     key_type=KEY_TYPE_TEAM)
    save_model_api_key(api_key)
    auth_header = create_jwt_token(secret=api_key.secret, client_id=str(api_key.service_id))

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))])

    app.celery.provider_tasks.deliver_sms.apply_async.assert_called_once_with([fake_uuid], queue='send-sms-tasks')
    assert response.status_code == 201


@pytest.mark.parametrize('template_type,queue_name', [
    (SMS_TYPE, 'send-sms-tasks'),
    (EMAIL_TYPE, 'send-email-tasks')
])
def test_should_persist_notification(
    client,
    sample_template,
    sample_email_template,
    fake_uuid,
    mocker,
    template_type,
    queue_name
):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(template_type))
    mocker.patch('app.notifications.process_notifications.uuid.uuid4', return_value=fake_uuid)

    template = sample_template if template_type == SMS_TYPE else sample_email_template
    to = sample_template.service.created_by.mobile_number if template_type == SMS_TYPE \
        else sample_email_template.service.created_by.email_address
    data = {
        'to': to,
        'template': template.id
    }
    api_key = ApiKey(
        service=template.service,
        name='team_key',
        created_by=template.created_by,
        key_type=KEY_TYPE_TEAM)
    save_model_api_key(api_key)
    auth_header = create_jwt_token(secret=api_key.secret, client_id=str(api_key.service_id))

    response = client.post(
        path='/notifications/{}'.format(template_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))])

    mocked.assert_called_once_with([fake_uuid], queue=queue_name)
    assert response.status_code == 201

    notification = notifications_dao.get_notification_by_id(fake_uuid)
    assert notification.to == to
    assert notification.template_id == template.id
    assert notification.notification_type == template_type


@pytest.mark.parametrize('template_type,queue_name', [
    (SMS_TYPE, 'send-sms-tasks'),
    (EMAIL_TYPE, 'send-email-tasks')
])
def test_should_delete_notification_and_return_error_if_sqs_fails(
    client,
    sample_email_template,
    sample_template,
    fake_uuid,
    mocker,
    template_type,
    queue_name
):
    mocked = mocker.patch(
        'app.celery.provider_tasks.deliver_{}.apply_async'.format(template_type),
        side_effect=Exception("failed to talk to SQS")
    )
    mocker.patch('app.notifications.process_notifications.uuid.uuid4', return_value=fake_uuid)

    template = sample_template if template_type == SMS_TYPE else sample_email_template
    to = sample_template.service.created_by.mobile_number if template_type == SMS_TYPE \
        else sample_email_template.service.created_by.email_address
    data = {
        'to': to,
        'template': template.id
    }
    api_key = ApiKey(
        service=template.service,
        name='team_key',
        created_by=template.created_by,
        key_type=KEY_TYPE_TEAM)
    save_model_api_key(api_key)
    auth_header = create_jwt_token(secret=api_key.secret, client_id=str(api_key.service_id))

    with pytest.raises(Exception) as e:
        client.post(
            path='/notifications/{}'.format(template_type),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))]
        )
    assert str(e.value) == 'failed to talk to SQS'

    mocked.assert_called_once_with([fake_uuid], queue=queue_name)
    assert not notifications_dao.get_notification_by_id(fake_uuid)
    assert not NotificationHistory.query.get(fake_uuid)


@pytest.mark.parametrize('to_email', [
    'simulate-delivered@notifications.service.gov.uk',
    'simulate-delivered-2@notifications.service.gov.uk',
    'simulate-delivered-3@notifications.service.gov.uk'
])
def test_should_not_persist_notification_or_send_email_if_simulated_email(
        client,
        to_email,
        sample_email_template,
        mocker):
    apply_async = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    data = {
        'to': to_email,
        'template': sample_email_template.id
    }

    auth_header = create_authorization_header(service_id=sample_email_template.service_id)

    response = client.post(
        path='/notifications/email',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201
    apply_async.assert_not_called()
    assert Notification.query.count() == 0


@pytest.mark.parametrize('to_sms', [
    '07700 900000',
    '07700 900111',
    '07700 900222'
])
def test_should_not_persist_notification_or_send_sms_if_simulated_number(
        client,
        to_sms,
        sample_template,
        mocker):
    apply_async = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'to': to_sms,
        'template': sample_template.id
    }

    auth_header = create_authorization_header(service_id=sample_template.service_id)

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201
    apply_async.assert_not_called()
    assert Notification.query.count() == 0


@pytest.mark.parametrize('key_type', [
    KEY_TYPE_NORMAL, KEY_TYPE_TEAM
])
@pytest.mark.parametrize('notification_type, to', [
    (SMS_TYPE, '07827992635'),
    (EMAIL_TYPE, 'non_whitelist_recipient@mail.com')]
)
def test_should_not_send_notification_to_non_whitelist_recipient_in_trial_mode(
    client,
    sample_service_whitelist,
    notification_type,
    to,
    key_type,
    mocker
):
    service = sample_service_whitelist.service
    service.restricted = True
    service.message_limit = 2

    apply_async = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))
    template = create_template(service, template_type=notification_type)
    assert sample_service_whitelist.service_id == service.id
    assert to not in [member.recipient for member in service.guest_list]

    create_notification(template=template)

    data = {
        'to': to,
        'template': str(template.id)
    }

    api_key = create_api_key(service, key_type=key_type)
    auth_header = create_jwt_token(secret=api_key.secret, client_id=str(api_key.service_id))

    response = client.post(
        path='/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))])

    expected_response_message = (
        'Can’t send to this recipient when service is in trial mode '
        '– see https://www.notifications.service.gov.uk/trial-mode'
    ) if key_type == KEY_TYPE_NORMAL else ('Can’t send to this recipient using a team-only API key')

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert expected_response_message in json_resp['message']['to']
    apply_async.assert_not_called()


@pytest.mark.parametrize('service_restricted', [
    True, False
])
@pytest.mark.parametrize('key_type', [
    KEY_TYPE_NORMAL, KEY_TYPE_TEAM
])
@pytest.mark.parametrize('notification_type, to', [
    (SMS_TYPE, '07123123123'),
    (EMAIL_TYPE, 'whitelist_recipient@mail.com')]
)
def test_should_send_notification_to_whitelist_recipient(
    client,
    sample_service,
    notification_type,
    to,
    key_type,
    service_restricted,
    mocker
):
    sample_service.message_limit = 2
    sample_service.restricted = service_restricted

    apply_async = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))
    template = create_template(sample_service, template_type=notification_type)
    if notification_type == SMS_TYPE:
        service_whitelist = create_service_whitelist(sample_service, mobile_number=to)
    elif notification_type == EMAIL_TYPE:
        service_whitelist = create_service_whitelist(sample_service, email_address=to)

    assert service_whitelist.service_id == sample_service.id
    assert to in [member.recipient for member in sample_service.guest_list]

    create_notification(template=template)

    data = {
        'to': to,
        'template': str(template.id)
    }

    sample_key = create_api_key(sample_service, key_type=key_type)
    auth_header = create_jwt_token(secret=sample_key.secret, client_id=str(sample_key.service_id))

    response = client.post(
        path='/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))])

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 201
    assert json_resp['data']['notification']['id']
    assert json_resp['data']['body'] == template.content
    assert json_resp['data']['template_version'] == template.version
    assert apply_async.called


@pytest.mark.parametrize(
    'notification_type, template_type, to', [
        (EMAIL_TYPE, SMS_TYPE, 'notify@digital.cabinet-office.gov.uk'),
        (SMS_TYPE, EMAIL_TYPE, '+447700900986')
    ])
def test_should_error_if_notification_type_does_not_match_template_type(
        client,
        sample_service,
        template_type,
        notification_type,
        to
):
    template = create_template(sample_service, template_type=template_type)
    data = {
        'to': to,
        'template': template.id
    }
    auth_header = create_authorization_header(service_id=template.service_id)
    response = client.post("/notifications/{}".format(notification_type),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['result'] == 'error'
    assert '{0} template is not suitable for {1} notification'.format(template_type, notification_type) \
           in json_resp['message']


def test_create_template_raises_invalid_request_exception_with_missing_personalisation(
        sample_template_with_placeholders):
    template = Template.query.get(sample_template_with_placeholders.id)
    from app.notifications.rest import create_template_object_for_notification
    with pytest.raises(InvalidRequest) as e:
        create_template_object_for_notification(template, {})
    assert {'template': ['Missing personalisation:  Name']} == e.value.message


def test_create_template_doesnt_raise_with_too_much_personalisation(
        sample_template_with_placeholders
):
    from app.notifications.rest import create_template_object_for_notification
    template = Template.query.get(sample_template_with_placeholders.id)
    create_template_object_for_notification(template, {'name': 'Jo', 'extra': 'stuff'})


@pytest.mark.parametrize(
    'template_type, should_error', [
        (SMS_TYPE, True),
        (EMAIL_TYPE, False)
    ]
)
def test_create_template_raises_invalid_request_when_content_too_large(
        sample_service,
        template_type,
        should_error
):
    sample = create_template(sample_service, template_type=template_type, content="((long_text))")
    template = Template.query.get(sample.id)
    from app.notifications.rest import create_template_object_for_notification
    try:
        create_template_object_for_notification(template,
                                                {'long_text':
                                                    ''.join(
                                                        random.choice(string.ascii_uppercase + string.digits) for _ in
                                                        range(SMS_CHAR_COUNT_LIMIT + 1))})
        if should_error:
            pytest.fail("expected an InvalidRequest")
    except InvalidRequest as e:
        if not should_error:
            pytest.fail("do not expect an InvalidRequest")
        assert e.message == {'content': ['Content has a character count greater than the limit of {}'.format(
            SMS_CHAR_COUNT_LIMIT)]}


@pytest.mark.parametrize("notification_type, send_to",
                         [("sms", "07700 900 855"),
                          ("email", "sample@email.com")])
def test_send_notification_uses_priority_queue_when_template_is_marked_as_priority(
    client,
    sample_service,
    mocker,
    notification_type,
    send_to,
):
    sample = create_template(sample_service, template_type=notification_type, process_type='priority')
    mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))

    data = {
        'to': send_to,
        'template': str(sample.id)
    }

    auth_header = create_authorization_header(service_id=sample.service_id)

    response = client.post(
        path='/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    response_data = json.loads(response.data)['data']
    notification_id = response_data['notification']['id']

    assert response.status_code == 201
    mocked.assert_called_once_with([notification_id], queue='priority-tasks')


@pytest.mark.parametrize(
    "notification_type, send_to",
    [("sms", "07700 900 855"), ("email", "sample@email.com")]
)
def test_returns_a_429_limit_exceeded_if_rate_limit_exceeded(
    client,
    sample_service,
    mocker,
    notification_type,
    send_to
):
    sample = create_template(sample_service, template_type=notification_type)
    persist_mock = mocker.patch('app.notifications.rest.persist_notification')
    deliver_mock = mocker.patch('app.notifications.rest.send_notification_to_queue')

    mocker.patch(
        'app.notifications.rest.check_rate_limiting',
        side_effect=RateLimitError("LIMIT", "INTERVAL", "TYPE"))

    data = {
        'to': send_to,
        'template': str(sample.id)
    }

    auth_header = create_authorization_header(service_id=sample.service_id)

    response = client.post(
        path='/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    message = json.loads(response.data)['message']
    result = json.loads(response.data)['result']
    assert response.status_code == 429
    assert result == 'error'
    assert message == 'Exceeded rate limit for key type TYPE of LIMIT requests per INTERVAL seconds'

    assert not persist_mock.called
    assert not deliver_mock.called


def test_should_allow_store_original_number_on_sms_notification(client, sample_template, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'to': '+(44) 7700-900 855',
        'template': str(sample_template.id)
    }

    auth_header = create_authorization_header(service_id=sample_template.service_id)

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    response_data = json.loads(response.data)['data']
    notification_id = response_data['notification']['id']

    mocked.assert_called_once_with([notification_id], queue='send-sms-tasks')
    assert response.status_code == 201
    assert notification_id
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert '+(44) 7700-900 855' == notifications[0].to


def test_should_not_allow_sending_to_international_number_without_international_permission(
    client, sample_template, mocker
):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'to': '20-12-1234-1234',
        'template': str(sample_template.id)
    }

    auth_header = create_authorization_header(service_id=sample_template.service_id)

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert not mocked.called
    assert response.status_code == 400
    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['result'] == 'error'
    assert error_json['message'] == 'Cannot send to international mobile numbers'


def test_should_allow_sending_to_crown_dependency_number_without_international_permission(
    client, mocker, notify_db_session
):
    service = create_service()

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    template = create_template(service)

    data = {
        'to': '07700-900-123',
        'template': str(template.id)
    }

    auth_header = create_authorization_header(service_id=service.id)

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201


def test_should_allow_sending_to_international_number_with_international_permission(
    client, sample_service_full_permissions, mocker
):
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    template = create_template(sample_service_full_permissions)

    data = {
        'to': '20-12-1234-1234',
        'template': str(template.id)
    }

    auth_header = create_authorization_header(service_id=sample_service_full_permissions.id)

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201


def test_should_not_allow_sms_notifications_if_service_permission_not_set(
    client,
    mocker,
    sample_template_without_sms_permission,
):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'to': '+447700900986',
        'template': str(sample_template_without_sms_permission.id)
    }

    auth_header = create_authorization_header(service_id=sample_template_without_sms_permission.service_id)

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert not mocked.called
    assert response.status_code == 400
    error_json = json.loads(response.get_data(as_text=True))

    assert error_json['result'] == 'error'
    assert error_json['message']['service'][0] == 'Cannot send text messages'


def test_should_not_allow_email_notifications_if_service_permission_not_set(
    client,
    mocker,
    sample_template_without_email_permission,
):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    data = {
        'to': 'notify@digital.cabinet-office.gov.uk',
        'template': str(sample_template_without_email_permission.id)
    }

    auth_header = create_authorization_header(service_id=sample_template_without_email_permission.service_id)

    response = client.post(
        path='/notifications/email',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert not mocked.called
    assert response.status_code == 400
    error_json = json.loads(response.get_data(as_text=True))

    assert error_json['result'] == 'error'
    assert error_json['message']['service'][0] == 'Cannot send emails'


@pytest.mark.parametrize(
    "notification_type, err_msg",
    [("letter", "letter notification type is not supported, please use the latest version of the client"),
     ("apple", "apple notification type is not supported")])
def test_should_throw_exception_if_notification_type_is_invalid(client, sample_service, notification_type, err_msg):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.post(
        path='/notifications/{}'.format(notification_type),
        data={},
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True))["message"] == err_msg


@pytest.mark.parametrize("notification_type, recipient",
                         [("sms", '07700 900 855'),
                          ("email", "test@gov.uk")
                          ]
                         )
def test_post_notification_should_set_reply_to_text(client, sample_service, mocker, notification_type,
                                                    recipient):
    mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))
    template = create_template(sample_service, template_type=notification_type)
    expected_reply_to = current_app.config['FROM_NUMBER']
    if notification_type == EMAIL_TYPE:
        expected_reply_to = 'reply_to@gov.uk'
        create_reply_to_email(service=sample_service, email_address=expected_reply_to, is_default=True)

    data = {
        'to': recipient,
        'template': str(template.id)
    }
    response = client.post("/notifications/{}".format(notification_type),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'),
                                    create_authorization_header(service_id=sample_service.id)]
                           )
    assert response.status_code == 201
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == expected_reply_to
