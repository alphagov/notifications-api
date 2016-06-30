from datetime import datetime, timedelta
import uuid

from flask import json
from notifications_python_client.authentication import create_jwt_token

import app.celery.tasks
from app.dao.notifications_dao import (
    get_notification_by_id,
    dao_get_notification_statistics_for_service,
    dao_update_notification
)
from app.dao.api_key_dao import save_model_api_key
from app.models import ApiKey, KEY_TYPE_NORMAL, KEY_TYPE_TEAM
from tests import create_authorization_header
from tests.app.conftest import sample_notification as create_sample_notification


def test_get_sms_notification_by_id(notify_api, sample_notification):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_notification.service_id)

            response = client.get(
                '/notifications/{}'.format(sample_notification.id),
                headers=[auth_header])

            assert response.status_code == 200
            notification = json.loads(response.get_data(as_text=True))['data']['notification']
            assert notification['status'] == 'created'
            assert notification['template'] == {
                'id': str(sample_notification.template.id),
                'name': sample_notification.template.name,
                'template_type': sample_notification.template.template_type}
            assert notification['job'] == {
                'id': str(sample_notification.job.id),
                'original_file_name': sample_notification.job.original_file_name
            }
            assert notification['to'] == '+447700900855'
            assert notification['service'] == str(sample_notification.service_id)
            assert notification['body'] == "This is a template"  # sample_template.content
            assert not notification.get('subject')


def test_get_email_notification_by_id(notify_api, notify_db, notify_db_session, sample_email_template):

    email_notification = create_sample_notification(notify_db,
                                                    notify_db_session,
                                                    service=sample_email_template.service,
                                                    template=sample_email_template,
                                                    status='sending')

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=email_notification.service_id)

            response = client.get(
                '/notifications/{}'.format(email_notification.id),
                headers=[auth_header])

            notification = json.loads(response.get_data(as_text=True))['data']['notification']

            assert notification['status'] == 'sending'
            assert notification['template'] == {
                'id': str(email_notification.template.id),
                'name': email_notification.template.name,
                'template_type': email_notification.template.template_type}
            assert notification['job'] == {
                'id': str(email_notification.job.id),
                'original_file_name': email_notification.job.original_file_name
            }

            assert notification['to'] == '+447700900855'
            assert notification['service'] == str(email_notification.service_id)
            assert response.status_code == 200
            assert notification['body'] == sample_email_template.content
            assert notification['subject'] == sample_email_template.subject


def test_get_notifications_empty_result(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            missing_notification_id = uuid.uuid4()
            auth_header = create_authorization_header(service_id=sample_api_key.service_id)

            response = client.get(
                path='/notifications/{}'.format(missing_notification_id),
                headers=[auth_header])

            notification = json.loads(response.get_data(as_text=True))
            assert notification['result'] == "error"
            assert notification['message'] == "No result found"
            assert response.status_code == 404


def test_get_real_notification_from_team_api_key_fails(notify_api, sample_notification):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        api_key = ApiKey(service=sample_notification.service,
                         name='api_key',
                         created_by=sample_notification.service.created_by,
                         key_type=KEY_TYPE_TEAM)
        save_model_api_key(api_key)

        response = client.get(
            path='/notifications/{}'.format(sample_notification.id),
            headers=_create_auth_header_from_key(api_key))
        notification = json.loads(response.get_data(as_text=True))
        assert response.status_code == 404
        assert notification['result'] == "error"
        assert notification['message'] == "No result found"


def test_get_team_notification_from_different_team_api_key_succeeds(notify_api, sample_notification):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        creation_api_key = ApiKey(service=sample_notification.service,
                                  name='creation_api_key',
                                  created_by=sample_notification.service.created_by,
                                  key_type=KEY_TYPE_TEAM)
        save_model_api_key(creation_api_key)

        querying_api_key = ApiKey(service=sample_notification.service,
                                  name='querying_api_key',
                                  created_by=sample_notification.service.created_by,
                                  key_type=KEY_TYPE_TEAM)
        save_model_api_key(querying_api_key)

        sample_notification.api_key = creation_api_key
        sample_notification.key_type = KEY_TYPE_TEAM
        dao_update_notification(sample_notification)

        response = client.get(
            path='/notifications/{}'.format(sample_notification.id),
            headers=_create_auth_header_from_key(querying_api_key))

        assert response.status_code == 200
        notification = json.loads(response.get_data(as_text=True))['data']['notification']
        assert sample_notification.api_key_id != querying_api_key.id
        assert notification['id'] == str(sample_notification.id)


def test_get_all_notifications(notify_api, sample_notification):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_notification.service_id)

            response = client.get(
                '/notifications',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert notifications['notifications'][0]['status'] == 'created'
            assert notifications['notifications'][0]['template'] == {
                'id': str(sample_notification.template.id),
                'name': sample_notification.template.name,
                'template_type': sample_notification.template.template_type}
            assert notifications['notifications'][0]['job'] == {
                'id': str(sample_notification.job.id),
                'original_file_name': sample_notification.job.original_file_name
            }

            assert notifications['notifications'][0]['to'] == '+447700900855'
            assert notifications['notifications'][0]['service'] == str(sample_notification.service_id)
            assert notifications['notifications'][0]['body'] == "This is a template"  # sample_template.content


def test_get_all_notifications_only_returns_notifications_of_matching_type(
    notify_api,
    notify_db,
    notify_db_session,
    sample_service
):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        team_api_key = ApiKey(service=sample_service,
                              name='team_api_key',
                              created_by=sample_service.created_by,
                              key_type=KEY_TYPE_TEAM)
        save_model_api_key(team_api_key)

        normal_api_key = ApiKey(service=sample_service,
                                name='normal_api_key',
                                created_by=sample_service.created_by,
                                key_type=KEY_TYPE_NORMAL)
        save_model_api_key(normal_api_key)

        normal_notification = create_sample_notification(
            notify_db,
            notify_db_session,
            api_key_id=normal_api_key.id,
            key_type=KEY_TYPE_NORMAL
        )
        team_notification = create_sample_notification(
            notify_db,
            notify_db_session,
            api_key_id=team_api_key.id,
            key_type=KEY_TYPE_TEAM
        )

        normal_response = client.get(
            path='/notifications',
            headers=_create_auth_header_from_key(normal_api_key))

        team_response = client.get(
            path='/notifications',
            headers=_create_auth_header_from_key(team_api_key))

        assert normal_response.status_code == 200
        assert team_response.status_code == 200

        normal_notifications = json.loads(normal_response.get_data(as_text=True))['notifications']
        assert len(normal_notifications) == 1
        assert normal_notifications[0]['id'] == str(normal_notification.id)

        team_notifications = json.loads(team_response.get_data(as_text=True))['notifications']
        assert len(team_notifications) == 1
        assert team_notifications[0]['id'] == str(team_notification.id)


def test_get_all_notifications_newest_first(notify_api, notify_db, notify_db_session, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification_1 = create_sample_notification(notify_db, notify_db_session, sample_email_template.service)
            notification_2 = create_sample_notification(notify_db, notify_db_session, sample_email_template.service)
            notification_3 = create_sample_notification(notify_db, notify_db_session, sample_email_template.service)

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 3
            assert notifications['notifications'][0]['to'] == notification_3.to
            assert notifications['notifications'][1]['to'] == notification_2.to
            assert notifications['notifications'][2]['to'] == notification_1.to
            assert response.status_code == 200


def test_should_reject_invalid_page_param(notify_api, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications?page=invalid',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert notifications['result'] == 'error'
            assert 'Not a valid integer.' in notifications['message']['page']


def test_valid_page_size_param(notify_api, notify_db, notify_db_session, sample_email_template):
    with notify_api.test_request_context():
        n1 = create_sample_notification(notify_db, notify_db_session)
        n2 = create_sample_notification(notify_db, notify_db_session)
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications?page=1&page_size=1',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(notifications['notifications']) == 1
            assert notifications['total'] == 2
            assert notifications['page_size'] == 1


def test_invalid_page_size_param(notify_api, notify_db, notify_db_session, sample_email_template):
    with notify_api.test_request_context():
        n1 = create_sample_notification(notify_db, notify_db_session)
        n2 = create_sample_notification(notify_db, notify_db_session)
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications?page=1&page_size=invalid',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert notifications['result'] == 'error'
            assert 'Not a valid integer.' in notifications['message']['page_size']


def test_should_return_pagination_links(notify_api, notify_db, notify_db_session, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # Effectively mocking page size
            original_page_size = notify_api.config['PAGE_SIZE']
            try:
                notify_api.config['PAGE_SIZE'] = 1

                create_sample_notification(notify_db, notify_db_session, sample_email_template.service)
                notification_2 = create_sample_notification(notify_db, notify_db_session, sample_email_template.service)
                create_sample_notification(notify_db, notify_db_session, sample_email_template.service)

                auth_header = create_authorization_header(service_id=sample_email_template.service_id)

                response = client.get(
                    '/notifications?page=2',
                    headers=[auth_header])

                notifications = json.loads(response.get_data(as_text=True))
                assert len(notifications['notifications']) == 1
                assert notifications['links']['last'] == '/notifications?page=3'
                assert notifications['links']['prev'] == '/notifications?page=1'
                assert notifications['links']['next'] == '/notifications?page=3'
                assert notifications['notifications'][0]['to'] == notification_2.to
                assert response.status_code == 200

            finally:
                notify_api.config['PAGE_SIZE'] = original_page_size


def test_get_all_notifications_returns_empty_list(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_api_key.service.id)

            response = client.get(
                '/notifications',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(notifications['notifications']) == 0


def test_filter_by_template_type(notify_api, notify_db, notify_db_session, sample_template, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_template)
            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications?template_type=sms',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 1
            assert notifications['notifications'][0]['template']['template_type'] == 'sms'
            assert response.status_code == 200


def test_filter_by_multiple_template_types(notify_api,
                                           notify_db,
                                           notify_db_session,
                                           sample_template,
                                           sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_template)
            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications?template_type=sms&template_type=email',
                headers=[auth_header])

            assert response.status_code == 200
            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 2
            set(['sms', 'email']) == set(
                [x['template']['template_type'] for x in notifications['notifications']])


def test_filter_by_status(notify_api, notify_db, notify_db_session, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template,
                status="delivered")

            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications?status=delivered',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 1
            assert notifications['notifications'][0]['status'] == 'delivered'
            assert response.status_code == 200


def test_filter_by_multiple_statuss(notify_api,
                                    notify_db,
                                    notify_db_session,
                                    sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template,
                status="delivered")

            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template,
                status='sending')

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications?status=delivered&status=sending',
                headers=[auth_header])

            assert response.status_code == 200
            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 2
            set(['delivered', 'sending']) == set(
                [x['status'] for x in notifications['notifications']])


def test_filter_by_status_and_template_type(notify_api,
                                            notify_db,
                                            notify_db_session,
                                            sample_template,
                                            sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_template)
            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)
            notification_3 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template,
                status="delivered")

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.get(
                '/notifications?template_type=email&status=delivered',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(notifications['notifications']) == 1
            assert notifications['notifications'][0]['template']['template_type'] == 'email'
            assert notifications['notifications'][0]['status'] == 'delivered'


def test_get_notification_by_id_returns_merged_template_content(notify_db,
                                                                notify_db_session,
                                                                notify_api,
                                                                sample_template_with_placeholders):

    sample_notification = create_sample_notification(notify_db,
                                                     notify_db_session,
                                                     template=sample_template_with_placeholders,
                                                     personalisation={"name": "world"})
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_notification.service_id)

            response = client.get(
                '/notifications/{}'.format(sample_notification.id),
                headers=[auth_header])

            notification = json.loads(response.get_data(as_text=True))['data']['notification']
            assert response.status_code == 200
            assert notification['body'] == 'Hello world'
            assert 'subject' not in notification


def test_get_notification_by_id_returns_merged_template_content_for_email(
    notify_db,
    notify_db_session,
    notify_api,
    sample_email_template_with_placeholders
):
    sample_notification = create_sample_notification(notify_db,
                                                     notify_db_session,
                                                     template=sample_email_template_with_placeholders,
                                                     personalisation={"name": "world"})
    with notify_api.test_request_context(), notify_api.test_client() as client:
        auth_header = create_authorization_header(service_id=sample_notification.service_id)

        response = client.get(
            '/notifications/{}'.format(sample_notification.id),
            headers=[auth_header])

        notification = json.loads(response.get_data(as_text=True))['data']['notification']
        assert response.status_code == 200
        assert notification['body'] == 'Hello world'
        assert notification['subject'] == 'world'


def test_get_notifications_for_service_returns_merged_template_content(notify_api,
                                                                       notify_db,
                                                                       notify_db_session,
                                                                       sample_template_with_placeholders):

    create_sample_notification(notify_db,
                               notify_db_session,
                               service=sample_template_with_placeholders.service,
                               template=sample_template_with_placeholders,
                               personalisation={"name": "merged with first"},
                               created_at=datetime.utcnow() - timedelta(seconds=1))

    create_sample_notification(notify_db,
                               notify_db_session,
                               service=sample_template_with_placeholders.service,
                               template=sample_template_with_placeholders,
                               personalisation={"name": "merged with second"})

    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header()

            response = client.get(
                path='/service/{}/notifications'.format(sample_template_with_placeholders.service.id),
                headers=[auth_header])
            assert response.status_code == 200

            resp = json.loads(response.get_data(as_text=True))
            assert len(resp['notifications']) == 2
            assert resp['notifications'][0]['body'] == 'Hello merged with first'
            assert resp['notifications'][1]['body'] == 'Hello merged with second'


def test_firetext_callback_should_not_need_auth(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&reference=send-sms-code&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            assert response.status_code == 200


def test_firetext_callback_should_return_400_if_empty_reference(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&reference=&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: reference missing']


def test_firetext_callback_should_return_400_if_no_reference(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: reference missing']


def test_firetext_callback_should_return_200_if_send_sms_reference(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=send-sms-code',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded: send-sms-code'


def test_firetext_callback_should_return_400_if_no_status(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&time=2016-03-10 14:17:00&reference=send-sms-code',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: status missing']


def test_firetext_callback_should_return_400_if_unknown_status(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=99&time=2016-03-10 14:17:00&reference={}'.format(uuid.uuid4()),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback failed: status 99 not found.'


def test_firetext_callback_should_return_400_if_invalid_guid_notification_id(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=1234',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback with invalid reference 1234'


def test_firetext_callback_should_return_404_if_cannot_find_notification_id(
    notify_db,
    notify_db_session,
    notify_api,
    mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            missing_notification_id = uuid.uuid4()
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    missing_notification_id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback failed: notification {} either not found ' \
                                           'or already updated from sending. Status {}'.format(
                missing_notification_id,
                'Delivered'
            )


def test_firetext_callback_should_update_notification_status(notify_api, sample_notification, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            original = get_notification_by_id(sample_notification.id)
            assert original.status == 'created'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    sample_notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                sample_notification.id
            )
            updated = get_notification_by_id(sample_notification.id)
            assert updated.status == 'delivered'
            assert get_notification_by_id(sample_notification.id).status == 'delivered'
            stats = dao_get_notification_statistics_for_service(sample_notification.service_id)[0]
            assert stats.sms_delivered == 1
            assert stats.sms_requested == 1
            assert stats.sms_failed == 0


def test_firetext_callback_should_update_notification_status_failed(notify_api, sample_notification, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            original = get_notification_by_id(sample_notification.id)
            assert original.status == 'created'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=1&time=2016-03-10 14:17:00&reference={}'.format(
                    sample_notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                sample_notification.id
            )
            assert get_notification_by_id(sample_notification.id).status == 'permanent-failure'
            stats = dao_get_notification_statistics_for_service(sample_notification.service_id)[0]
            assert stats.sms_delivered == 0
            assert stats.sms_requested == 1
            assert stats.sms_failed == 1


def test_firetext_callback_should_update_notification_status_pending(notify_api, notify_db, notify_db_session, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            notification = create_sample_notification(notify_db, notify_db_session, status='sending')
            original = get_notification_by_id(notification.id)
            assert original.status == 'sending'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=2&time=2016-03-10 14:17:00&reference={}'.format(
                    notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                notification.id
            )
            assert get_notification_by_id(notification.id).status == 'pending'
            stats = dao_get_notification_statistics_for_service(notification.service_id)[0]
            assert stats.sms_delivered == 0
            assert stats.sms_requested == 1
            assert stats.sms_failed == 0


def test_firetext_callback_should_update_multiple_notification_status_sent(
    notify_api,
    notify_db,
    notify_db_session,
    mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            notification1 = create_sample_notification(notify_db, notify_db_session, status='sending')
            notification2 = create_sample_notification(notify_db, notify_db_session, status='sending')
            notification3 = create_sample_notification(notify_db, notify_db_session, status='sending')

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification1.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification2.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification3.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            stats = dao_get_notification_statistics_for_service(notification1.service_id)[0]
            assert stats.sms_delivered == 3
            assert stats.sms_requested == 3
            assert stats.sms_failed == 0


def test_process_mmg_response_return_200_when_cid_is_send_sms_code(notify_api):
    with notify_api.test_request_context():
        data = '{"reference": "10100164", "CID": "send-sms-code", "MSISDN": "447775349060", "status": "3", \
        "deliverytime": "2016-04-05 16:01:07"}'

        with notify_api.test_client() as client:
            response = client.post(path='notifications/sms/mmg',
                                   data=data,
                                   headers=[('Content-Type', 'application/json')])
            assert response.status_code == 200
            json_data = json.loads(response.data)
            assert json_data['result'] == 'success'
            assert json_data['message'] == 'MMG callback succeeded: send-sms-code'


def test_process_mmg_response_returns_200_when_cid_is_valid_notification_id(notify_api, sample_notification):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(sample_notification.id),
                           "MSISDN": "447777349060",
                           "status": "3",
                           "deliverytime": "2016-04-05 16:01:07"})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(sample_notification.id)
        assert get_notification_by_id(sample_notification.id).status == 'delivered'


def test_process_mmg_response_status_5_updates_notification_with_permanently_failed(notify_api,
                                                                                    sample_notification):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(sample_notification.id),
                           "MSISDN": "447777349060",
                           "status": 5})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(sample_notification.id)
        assert get_notification_by_id(sample_notification.id).status == 'permanent-failure'


def test_process_mmg_response_status_2_updates_notification_with_temporary_failed(notify_api,
                                                                                  sample_notification):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(sample_notification.id),
                           "MSISDN": "447777349060",
                           "status": 2})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(sample_notification.id)
        assert get_notification_by_id(sample_notification.id).status == 'temporary-failure'


def test_process_mmg_response_status_4_updates_notification_with_temporary_failed(notify_api,
                                                                                  sample_notification):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(sample_notification.id),
                           "MSISDN": "447777349060",
                           "status": 4})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(sample_notification.id)
        assert get_notification_by_id(sample_notification.id).status == 'temporary-failure'


def test_process_mmg_response_unknown_status_updates_notification_with_failed(notify_api,
                                                                              sample_notification):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(sample_notification.id),
                           "MSISDN": "447777349060",
                           "status": 10})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(sample_notification.id)
        assert get_notification_by_id(sample_notification.id).status == 'failed'


def test_process_mmg_response_returns_400_for_malformed_data(notify_api):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "monkey": 'random thing',
                           "MSISDN": "447777349060",
                           "no_status": 00,
                           "deliverytime": "2016-04-05 16:01:07"})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 400
        json_data = json.loads(response.data)
        assert json_data['result'] == 'error'
        assert len(json_data['message']) == 2
        assert "{} callback failed: {} missing".format('MMG', 'status') in json_data['message']
        assert "{} callback failed: {} missing".format('MMG', 'CID') in json_data['message']


def test_ses_callback_should_not_need_auth(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            assert response.status_code == 404


def test_ses_callback_should_fail_if_invalid_json(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data="nonsense",
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: invalid json'


def test_ses_callback_should_fail_if_invalid_notification_type(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_invalid_notification_type_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: status Unknown not found'


def test_ses_callback_should_fail_if_missing_message_id(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_missing_notification_id_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: messageId missing'


def test_ses_callback_should_fail_if_notification_cannot_be_found(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_invalid_notification_id_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: notification either not found or already updated from sending. Status delivered'  # noqa


def test_ses_callback_should_update_notification_status(
        notify_api,
        notify_db,
        notify_db_session,
        sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='sending'
            )

            assert get_notification_by_id(notification.id).status == 'sending'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'
            assert get_notification_by_id(notification.id).status == 'delivered'
            stats = dao_get_notification_statistics_for_service(notification.service_id)[0]
            assert stats.emails_delivered == 1
            assert stats.emails_requested == 1
            assert stats.emails_failed == 0


def test_ses_callback_should_update_multiple_notification_status_sent(
        notify_api,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification1 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref1',
                status='sending')

            notification2 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref2',
                status='sending')

            notification3 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref3',
                status='sending')

            resp1 = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(ref='ref1'),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            resp2 = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(ref='ref2'),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            resp3 = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(ref='ref3'),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )

            assert resp1.status_code == 200
            assert resp2.status_code == 200
            assert resp3.status_code == 200

            stats = dao_get_notification_statistics_for_service(notification1.service_id)[0]
            assert stats.emails_delivered == 3
            assert stats.emails_requested == 3
            assert stats.emails_failed == 0


def test_ses_callback_should_update_record_statsd(
        notify_api,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')

            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='sending'
            )

            assert get_notification_by_id(notification.id).status == 'sending'

            client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            app.statsd_client.incr.assert_called_once_with("notifications.callback.ses.delivered")


def test_ses_callback_should_set_status_to_temporary_failure(notify_api,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='sending'
            )

            assert get_notification_by_id(notification.id).status == 'sending'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_soft_bounce_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'
            assert get_notification_by_id(notification.id).status == 'temporary-failure'
            stats = dao_get_notification_statistics_for_service(notification.service_id)[0]
            assert stats.emails_delivered == 0
            assert stats.emails_requested == 1
            assert stats.emails_failed == 1


def test_ses_callback_should_not_set_status_once_status_is_delivered(notify_api,
                                                                     notify_db,
                                                                     notify_db_session,
                                                                     sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='delivered'
            )

            assert get_notification_by_id(notification.id).status == 'delivered'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_soft_bounce_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: notification either not found or already updated from sending. Status temporary-failure'  # noqa
            assert get_notification_by_id(notification.id).status == 'delivered'


def test_ses_callback_should_set_status_to_permanent_failure(notify_api,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='sending'
            )

            assert get_notification_by_id(notification.id).status == 'sending'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_hard_bounce_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'
            assert get_notification_by_id(notification.id).status == 'permanent-failure'
            stats = dao_get_notification_statistics_for_service(notification.service_id)[0]
            assert stats.emails_delivered == 0
            assert stats.emails_requested == 1
            assert stats.emails_failed == 1


def test_should_handle_invite_email_callbacks(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notify_api.config['INVITATION_EMAIL_FROM'] = 'test-invite'
            notify_api.config['NOTIFY_EMAIL_DOMAIN'] = 'test-domain.com'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_invite_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'


def test_should_handle_validation_code_callbacks(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notify_api.config['VERIFY_CODE_FROM_EMAIL_ADDRESS'] = 'valid-code@test.com'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_validation_code_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'


def test_process_mmg_response_records_statsd(notify_api, sample_notification, mocker):
    with notify_api.test_client() as client:
        mocker.patch('app.statsd_client.incr')
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(sample_notification.id),
                           "MSISDN": "447777349060",
                           "status": "3",
                           "deliverytime": "2016-04-05 16:01:07"})

        client.post(path='notifications/sms/mmg',
                    data=data,
                    headers=[('Content-Type', 'application/json')])
        assert app.statsd_client.incr.call_count == 2
        app.statsd_client.incr.assert_any_call("notifications.callback.mmg.delivered")
        app.statsd_client.incr.assert_any_call("notifications.callback.mmg.status.3")


def test_firetext_callback_should_record_statsd(notify_api, notify_db, notify_db_session, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            notification = create_sample_notification(notify_db, notify_db_session, status='sending')

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&code=101&reference={}'.format(
                    notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            assert app.statsd_client.incr.call_count == 3
            app.statsd_client.incr.assert_any_call("notifications.callback.firetext.code.101")
            app.statsd_client.incr.assert_any_call("notifications.callback.firetext.status.0")
            app.statsd_client.incr.assert_any_call("notifications.callback.firetext.delivered")


def ses_validation_code_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"valid-code@test.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"ref\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.u\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_invite_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test-invite@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"ref\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.u\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_notification_callback(ref='ref'):
    return str.encode(
        '{\n  "Type" : "Notification",\n  "MessageId" : "%(ref)s",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"%(ref)s\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}' % {'ref': ref}  # noqa
    )


def ses_invalid_notification_id_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "missing",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"missing\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_missing_notification_id_callback():
    return b'{\n  "Type" : "Notification",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_invalid_notification_type_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Unknown\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_hard_bounce_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Bounce\\",\\"bounce\\":{\\"bounceType\\":\\"Permanent\\",\\"bounceSubType\\":\\"General\\"}, \\"mail\\":{\\"messageId\\":\\"ref\\",\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_soft_bounce_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Bounce\\",\\"bounce\\":{\\"bounceType\\":\\"Undetermined\\",\\"bounceSubType\\":\\"General\\"}, \\"mail\\":{\\"messageId\\":\\"ref\\",\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def _create_auth_header_from_key(api_key):
    token = create_jwt_token(secret=api_key.unsigned_secret, client_id=str(api_key.service_id))
    return [('Authorization', 'Bearer {}'.format(token))]
