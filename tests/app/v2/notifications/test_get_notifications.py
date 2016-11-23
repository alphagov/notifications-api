import json

from app import DATETIME_FORMAT
from tests import create_authorization_header


def test_get_notification_by_id_returns_200(client, sample_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)

    response = client.get(
        path='/v2/notifications/{}'.format(sample_notification.id),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    expected_template_response = {
        'id': '{}'.format(sample_notification.serialize()['template']['id']),
        'version': sample_notification.serialize()['template']['version'],
        'uri': sample_notification.serialize()['template']['uri']
    }

    expected_response = {
        'id': '{}'.format(sample_notification.id),
        'reference': None,
        'email_address': None,
        'phone_number': '{}'.format(sample_notification.to),
        'line_1': None,
        'line_2': None,
        'line_3': None,
        'line_4': None,
        'line_5': None,
        'line_6': None,
        'postcode': None,
        'cost': sample_notification.cost(),
        'type': '{}'.format(sample_notification.notification_type),
        'status': '{}'.format(sample_notification.status),
        'template': expected_template_response,
        'created_at': sample_notification.created_at.strftime(DATETIME_FORMAT),
        'sent_at': sample_notification.sent_at,
        'completed_at': sample_notification.completed_at()
    }

    assert json_response == expected_response
