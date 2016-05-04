import json
from datetime import (date, timedelta)
from flask import url_for
from tests import create_authorization_header


def test_fragment_count(notify_api, sample_provider_statistics):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            endpoint = url_for(
                'service.get_service_provider_aggregate_statistics',
                service_id=str(sample_provider_statistics.service.id))
            auth_header = create_authorization_header()
            resp = client.get(
                endpoint,
                headers=[auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['sms_count'] == 1


def test_fragment_count_from_to(notify_api, sample_provider_statistics):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            today_str = date.today().strftime('%Y-%m-%d')
            endpoint = url_for(
                'service.get_service_provider_aggregate_statistics',
                service_id=str(sample_provider_statistics.service.id),
                date_from=today_str,
                date_to=today_str)
            auth_header = create_authorization_header()
            resp = client.get(
                endpoint,
                headers=[auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['sms_count'] == 1


def test_fragment_count_from_greater_than_to(notify_api, sample_provider_statistics):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            today_str = date.today().strftime('%Y-%m-%d')
            yesterday_str = date.today() - timedelta(days=1)
            endpoint = url_for(
                'service.get_service_provider_aggregate_statistics',
                service_id=str(sample_provider_statistics.service.id),
                date_from=today_str,
                date_to=yesterday_str)
            auth_header = create_authorization_header()
            resp = client.get(
                endpoint,
                headers=[auth_header]
            )
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert 'date_from needs to be greater than date_to' in json_resp['message']['_schema']


def test_fragment_count_in_future(notify_api, sample_provider_statistics):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            tomorrow_str = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
            endpoint = url_for(
                'service.get_service_provider_aggregate_statistics',
                service_id=str(sample_provider_statistics.service.id),
                date_from=tomorrow_str)
            auth_header = create_authorization_header()
            resp = client.get(
                endpoint,
                headers=[auth_header]
            )
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert 'Date cannot be in the future' in json_resp['message']['date_from']
