from datetime import datetime, timedelta
import uuid

import pytest
from flask import json
from notifications_python_client.authentication import create_jwt_token

from app.dao.notifications_dao import dao_update_notification
from app.dao.api_key_dao import save_model_api_key
from app.models import ApiKey, KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST
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


@pytest.mark.parametrize('key_type', [KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST])
def test_get_notification_from_different_api_key_of_same_type_succeeds(notify_api, sample_notification, key_type):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        creation_api_key = ApiKey(service=sample_notification.service,
                                  name='creation_api_key',
                                  created_by=sample_notification.service.created_by,
                                  key_type=key_type)
        save_model_api_key(creation_api_key)

        querying_api_key = ApiKey(service=sample_notification.service,
                                  name='querying_api_key',
                                  created_by=sample_notification.service.created_by,
                                  key_type=key_type)
        save_model_api_key(querying_api_key)

        sample_notification.api_key = creation_api_key
        sample_notification.key_type = key_type
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


@pytest.mark.parametrize('key_type', [KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST])
def test_get_all_notifications_only_returns_notifications_of_matching_type(
    notify_api,
    notify_db,
    notify_db_session,
    sample_service,
    key_type
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

        test_api_key = ApiKey(service=sample_service,
                              name='test_api_key',
                              created_by=sample_service.created_by,
                              key_type=KEY_TYPE_TEST)
        save_model_api_key(test_api_key)

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
        test_notification = create_sample_notification(
            notify_db,
            notify_db_session,
            api_key_id=test_api_key.id,
            key_type=KEY_TYPE_TEST
        )

        notification_objs = {
            KEY_TYPE_NORMAL: normal_notification,
            KEY_TYPE_TEAM: team_notification,
            KEY_TYPE_TEST: test_notification
        }

        response = client.get(
            path='/notifications',
            headers=_create_auth_header_from_key(notification_objs[key_type].api_key))

        assert response.status_code == 200

        notifications = json.loads(response.get_data(as_text=True))['notifications']
        assert len(notifications) == 1
        assert notifications[0]['id'] == str(notification_objs[key_type].id)


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


def _create_auth_header_from_key(api_key):
    token = create_jwt_token(secret=api_key.unsigned_secret, client_id=str(api_key.service_id))
    return [('Authorization', 'Bearer {}'.format(token))]
