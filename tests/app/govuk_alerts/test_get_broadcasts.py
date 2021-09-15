from datetime import datetime

from flask import current_app, json

from app.models import BROADCAST_TYPE
from tests import create_internal_authorization_header
from tests.app.db import create_broadcast_message, create_template


def test_get_all_broadcasts_returns_list_of_broadcasts_and_200(
    client, sample_broadcast_service
):
    template_1 = create_template(sample_broadcast_service, BROADCAST_TYPE)

    broadcast_message_1 = create_broadcast_message(
        template_1,
        starts_at=datetime(2021, 6, 15, 12, 0, 0),
        status='cancelled')

    broadcast_message_2 = create_broadcast_message(
        template_1,
        starts_at=datetime(2021, 6, 22, 12, 0, 0),
        status='broadcasting')

    jwt_client_id = current_app.config['GOVUK_ALERTS_CLIENT_ID']
    header = create_internal_authorization_header(jwt_client_id)

    response = client.get('/govuk-alerts', headers=[header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert len(json_response['alerts']) == 2

    assert json_response['alerts'][0]['id'] == str(broadcast_message_2.id)
    assert json_response['alerts'][0]['starts_at'] == '2021-06-22T12:00:00.000000Z'
    assert json_response['alerts'][0]['finishes_at'] is None
    assert json_response['alerts'][1]['id'] == str(broadcast_message_1.id)
    assert json_response['alerts'][1]['starts_at'] == '2021-06-15T12:00:00.000000Z'
