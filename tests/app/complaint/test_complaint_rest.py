import json

from tests import create_authorization_header
from tests.app.db import create_complaint, create_service, create_template, create_notification


def test_get_all_complaints_returns_list_for_multiple_services_and_complaints(client, notify_db_session):
    service = create_service(service_name='service1')
    template = create_template(service=service)
    notification = create_notification(template=template)
    complaint_1 = create_complaint()  # default service
    complaint_2 = create_complaint(service=service, notification=notification)

    response = client.get('/complaint', headers=[create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == [complaint_2.serialize(), complaint_1.serialize()]


def test_get_all_complaints_returns_empty_list(client):
    response = client.get('/complaint', headers=[create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == []
