import pytest
import requests_mock
from requests import RequestException

from app.dao.templates_dao import dao_update_template
from app.models import BROADCAST_TYPE, BroadcastStatusType
from app.celery.broadcast_message_tasks import send_broadcast_message
from tests.app.db import create_template, create_broadcast_message


def test_send_broadcast_message_sends_data_correctly(sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, areas=['london'], status=BroadcastStatusType.BROADCASTING)

    with requests_mock.Mocker() as request_mock:
        request_mock.post("http://test-cbc-proxy/broadcasts/stub-1", json={'valid': 'true'}, status_code=200)
        send_broadcast_message(broadcast_message_id=str(bm.id))

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].method == 'POST'
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"

    cbc_json = request_mock.request_history[0].json()
    assert cbc_json['template']['id'] == str(t.id)
    assert cbc_json['template']['template_type'] == BROADCAST_TYPE
    assert cbc_json['broadcast_message']['areas'] == ['london']


def test_send_broadcast_message_sends_old_version_of_template(sample_service):
    t = create_template(sample_service, BROADCAST_TYPE, content='first content')
    bm = create_broadcast_message(t, areas=['london'], status=BroadcastStatusType.BROADCASTING)

    t.content = 'second content'
    dao_update_template(t)
    assert t.version == 2

    with requests_mock.Mocker() as request_mock:
        request_mock.post("http://test-cbc-proxy/broadcasts/stub-1", json={'valid': 'true'}, status_code=200)
        send_broadcast_message(broadcast_message_id=str(bm.id))

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].method == 'POST'
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"

    cbc_json = request_mock.request_history[0].json()
    assert cbc_json['template']['id'] == str(t.id)
    assert cbc_json['template']['version'] == 1
    assert cbc_json['template']['content'] == 'first content'


def test_send_broadcast_message_errors(sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.BROADCASTING)

    with requests_mock.Mocker() as request_mock:
        request_mock.post("http://test-cbc-proxy/broadcasts/stub-1", text='503 bad gateway', status_code=503)
        # we're not retrying or anything for the moment - but this'll ensure any exception gets logged
        with pytest.raises(RequestException) as ex:
            send_broadcast_message(broadcast_message_id=str(bm.id))

    assert ex.value.response.status_code == 503
