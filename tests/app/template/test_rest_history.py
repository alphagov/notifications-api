import json
from datetime import (datetime, date)
from flask import url_for
from app.dao.templates_dao import dao_update_template
from tests import create_authorization_header
from tests.app.db import create_letter_contact


def test_template_history_version(notify_api, sample_user, sample_template):
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
            assert json_resp['data']['created_by']['name'] == sample_user.name
            assert datetime.strptime(json_resp['data']['created_at'], '%Y-%m-%d %H:%M:%S.%f').date() == date.today()


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


def test_all_versions_of_template(notify_api, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            old_content = sample_template.content
            newer_content = "Newer content"
            newest_content = "Newest content"
            sample_template.content = newer_content
            dao_update_template(sample_template)
            sample_template.content = newest_content
            dao_update_template(sample_template)
            auth_header = create_authorization_header()
            endpoint = url_for(
                'template.get_template_versions',
                service_id=sample_template.service.id,
                template_id=sample_template.id
            )
            resp = client.get(
                endpoint,
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert len(json_resp['data']) == 3
            assert json_resp['data'][0]['content'] == newest_content
            assert json_resp['data'][0]['updated_at']
            assert json_resp['data'][1]['content'] == newer_content
            assert json_resp['data'][1]['updated_at']
            assert json_resp['data'][2]['content'] == old_content


def test_update_template_reply_to_updates_history(client, sample_letter_template):
    auth_header = create_authorization_header()
    letter_contact = create_letter_contact(sample_letter_template.service, "Edinburgh, ED1 1AA")

    sample_letter_template.reply_to = letter_contact.id
    dao_update_template(sample_letter_template)

    resp = client.get(
        '/service/{}/template/{}/version/2'.format(sample_letter_template.service_id, sample_letter_template.id),
        headers=[auth_header]
    )
    assert resp.status_code == 200

    hist_json_resp = json.loads(resp.get_data(as_text=True))
    assert 'service_letter_contact_id' not in hist_json_resp['data']
    assert hist_json_resp['data']['reply_to'] == str(letter_contact.id)
    assert hist_json_resp['data']['reply_to_text'] == letter_contact.contact_block
