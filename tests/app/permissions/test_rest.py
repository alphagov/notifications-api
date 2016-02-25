import json
from flask import url_for
from tests import create_authorization_header
from ..conftest import sample_permission as create_permission


def test_get_permission_list(notify_api, notify_db, notify_db_session, sample_permission):
    """
    Tests GET endpoint '/' to retrieve entire permission list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(
                path=url_for('permission.get_permissions'),
                method='GET')
            response = client.get(
                url_for('permission.get_permissions'),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 1
            expected = {
                "permission": sample_permission.permission,
                "user": sample_permission.user.id,
                "id": sample_permission.id,
                "service": None
            }
            assert expected in json_resp['data']


def test_get_permission_filter(notify_api,
                               notify_db,
                               notify_db_session,
                               sample_permission,
                               sample_user,
                               sample_service):
    """
    Tests GET endpoint '/' to retrieve filtered permission list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            another_permission = create_permission(
                notify_db,
                notify_db_session,
                user=sample_user,
                service=sample_service,
                permission="another permission")
            header = create_authorization_header(
                path=url_for('permission.get_permissions'),
                method='GET')
            response = client.get(
                url_for('permission.get_permissions', service=str(sample_service.id)),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 1
            expected = {
                "permission": another_permission.permission,
                "user": sample_user.id,
                "id": another_permission.id,
                "service": str(sample_service.id)
            }
            assert expected in json_resp['data']


def test_get_permission(notify_api, notify_db, notify_db_session, sample_permission):
    """
    Tests GET endpoint '/<permission_id>' to retrieve a single permission.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(
                path=url_for('permission.get_permission', permission_id=sample_permission.id),
                method='GET')
            response = client.get(
                url_for('permission.get_permission', permission_id=sample_permission.id),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            expected = {
                "permission": sample_permission.permission,
                "user": sample_permission.user.id,
                "id": sample_permission.id,
                "service": None
            }
            assert expected == json_resp['data']


def test_create_permission(notify_api, notify_db, notify_db_session, sample_user, sample_service):
    """
    Tests POST endpoint '/' to create a single permission.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            permission_name = "new permission"
            data = json.dumps({
                'user': sample_user.id,
                'service': str(sample_service.id),
                'permission': permission_name})
            auth_header = create_authorization_header(
                path=url_for('permission.create_permission'),
                method='POST',
                request_body=data)
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                url_for('permission.create_permission'),
                data=data,
                headers=headers)
            assert response.status_code == 201
            json_resp = json.loads(response.get_data(as_text=True))
            assert permission_name == json_resp['data']['permission']
            assert str(sample_service.id) == json_resp['data']['service']
            assert sample_user.id == json_resp['data']['user']


def test_create_permission_no_service(notify_api, notify_db, notify_db_session, sample_user):
    """
    Tests POST endpoint '/' to create a single permission.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            permission_name = "new permission"
            data = json.dumps({
                'user': sample_user.id,
                'permission': permission_name})
            auth_header = create_authorization_header(
                path=url_for('permission.create_permission'),
                method='POST',
                request_body=data)
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                url_for('permission.create_permission'),
                data=data,
                headers=headers)
            assert response.status_code == 201
            json_resp = json.loads(response.get_data(as_text=True))
            assert permission_name == json_resp['data']['permission']
            assert sample_user.id == json_resp['data']['user']


def test_delete_permission(notify_api, notify_db, notify_db_session, sample_permission):
    """
    Tests DELETE endpoint '/' to delete a permission.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(
                path=url_for('permission.delete_permission', permission_id=sample_permission.id),
                method='DELETE')
            response = client.delete(
                url_for('permission.delete_permission', permission_id=sample_permission.id),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            expected = {
                "permission": sample_permission.permission,
                "user": sample_permission.user.id,
                "id": sample_permission.id,
                "service": None
            }
            assert expected == json_resp['data']
