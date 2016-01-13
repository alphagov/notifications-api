import json
from app.models import Template
from flask import url_for


def test_get_template_list(notify_api, notify_db, notify_db_session, sample_template):
    """
    Tests GET endpoint '/' to retrieve entire template list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('template.get_template'))
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 1
            assert json_resp['data'][0]['name'] == sample_template.name
            assert json_resp['data'][0]['id'] == sample_template.id


def test_get_template(notify_api, notify_db, notify_db_session, sample_template):
    """
    Tests GET endpoint '/<template_id>' to retrieve a single template.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            resp = client.get(url_for(
                'template.get_template', template_id=sample_template.id))
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == sample_template.name
            assert json_resp['data']['id'] == sample_template.id
