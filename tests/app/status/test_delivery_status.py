import json

from datetime import (
    datetime,
    timedelta
)

from tests.app.conftest import sample_notification


def test_get_delivery_status_all_ok(notify_api, notify_db):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/_delivery_status'
            response = client.get(path)
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['status'] == 'ok'
            assert resp_json['message'] == '0 notifications in sending state over 5 minutes'


def test_get_delivery_status_with_undelivered_notification(notify_api, notify_db, notify_db_session):

    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session, status='sending')
    more_than_five_mins_ago = datetime.utcnow() - timedelta(minutes=10)
    notification.created_at = more_than_five_mins_ago
    notify_db.session.add(notification)
    notify_db.session.commit()

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/_delivery_status'
            response = client.get(path)
            assert response.status_code == 500
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['status'] == 'error'
            assert resp_json['message'] == '1 notifications in sending state over 5 minutes'
