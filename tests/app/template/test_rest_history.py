import json
from flask import url_for
from app.models import Template
from app.dao.templates_dao import dao_update_template
from tests import create_authorization_header


def test_template_history_version(notify_api, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            endpoint = url_for(
                'template.get_template_version',
                service_id=sample_template.service.id,
                template_id=sample_template.id,
                version=1)
            resp = client.get(
                endpoint,
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['id'] == str(sample_template.id)
            assert json_resp['data']['content'] == sample_template.content
            assert json_resp['data']['version'] == 1


def test_previous_template_history_version(notify_api, sample_template):
    old_content = sample_template.content
    sample_template.content = "New content"
    dao_update_template(sample_template)
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            endpoint = url_for(
                'template.get_template_version',
                service_id=sample_template.service.id,
                template_id=sample_template.id,
                version=1)
            resp = client.get(
                endpoint,
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['id'] == str(sample_template.id)
            assert json_resp['data']['version'] == 1
            assert json_resp['data']['content'] == old_content


def test_404_missing_template_version(notify_api, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            endpoint = url_for(
                'template.get_template_version',
                service_id=sample_template.service.id,
                template_id=sample_template.id,
                version=2)
            resp = client.get(
                endpoint,
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 404
