import json
from flask import url_for
from app.models import Permission
from tests import create_authorization_header
from ..conftest import sample_permission as create_permission


def test_get_permission_list(notify_api, notify_db, notify_db_session, sample_permission):
    """
    Tests GET endpoint '/' to retrieve entire permission list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header()
            response = client.get(
                url_for('permission.get_permissions'),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 1
            expected = {
                "permission": sample_permission.permission,
                "user": str(sample_permission.user.id),
                "id": str(sample_permission.id),
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
            header = create_authorization_header()
            response = client.get(
                url_for('permission.get_permissions', service=str(sample_service.id)),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            another_permission = Permission.query.filter_by(
                service_id=str(sample_service.id)).first()
            expected = {
                "permission": another_permission.permission,
                "user": str(sample_user.id),
                "id": str(another_permission.id),
                "service": str(sample_service.id)
            }
            assert expected in json_resp['data']


def test_get_permission(notify_api, notify_db, notify_db_session, sample_permission):
    """
    Tests GET endpoint '/<permission_id>' to retrieve a single permission.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header()
            response = client.get(
                url_for('permission.get_permission', permission_id=str(sample_permission.id)),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            expected = {
                "permission": sample_permission.permission,
                "user": str(sample_permission.user.id),
                "id": str(sample_permission.id),
                "service": None
            }
            assert expected == json_resp['data']


def test_get_permission_404(notify_api, notify_db, notify_db_session, sample_permission):
    """
    Tests GET endpoint '/<invalid_id>' returns a correct 404
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header()
            response = client.get(
                url_for('permission.get_permission', permission_id="123"),
                headers=[header])
            assert response.status_code == 404
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['message'] == 'No result found'
