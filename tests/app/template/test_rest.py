import json
from flask import url_for

from tests import create_authorization_header


def test_get_template_list(notify_api, notify_db, notify_db_session, sample_template):
    """
    Tests GET endpoint '/' to retrieve entire template list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_template.service_id,
                                                      path=url_for('template.get_template'),
                                                      method='GET')
            response = client.get(url_for('template.get_template'),
                                  headers=[auth_header])
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
            auth_header = create_authorization_header(service_id=sample_template.service_id,
                                                      path=url_for('template.get_template',
                                                                   template_id=sample_template.id),
                                                      method='GET')
            resp = client.get(url_for(
                'template.get_template', template_id=sample_template.id),
                headers=[auth_header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == sample_template.name
            assert json_resp['data']['id'] == sample_template.id
