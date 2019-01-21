from urllib import parse

import requests
import pytest

from app.cronitor import cronitor

from tests.conftest import set_config_values


def _cronitor_url(key, command):
    return parse.urlunparse(parse.ParseResult(
        scheme='https',
        netloc='cronitor.link',
        path='{}/{}'.format(key, command),
        params='',
        query=parse.urlencode({'host': 'http://localhost:6011'}),
        fragment=''
    ))


RUN_LINK = _cronitor_url('secret', 'run')
FAIL_LINK = _cronitor_url('secret', 'fail')
COMPLETE_LINK = _cronitor_url('secret', 'complete')


@cronitor('hello')
def successful_task():
    return 1


@cronitor('hello')
def crashing_task():
    raise ValueError


def test_cronitor_sends_run_and_complete(notify_api, rmock):
    rmock.get(RUN_LINK, status_code=200)
    rmock.get(COMPLETE_LINK, status_code=200)

    with set_config_values(notify_api, {
        'CRONITOR_ENABLED': True,
        'CRONITOR_KEYS': {'hello': 'secret'}
    }):
        assert successful_task() == 1

    assert rmock.call_count == 2
    assert rmock.request_history[0].url == RUN_LINK
    assert rmock.request_history[1].url == COMPLETE_LINK


def test_cronitor_sends_run_and_fail_if_exception(notify_api, rmock):
    rmock.get(RUN_LINK, status_code=200)
    rmock.get(FAIL_LINK, status_code=200)

    with set_config_values(notify_api, {
        'CRONITOR_ENABLED': True,
        'CRONITOR_KEYS': {'hello': 'secret'}
    }):
        with pytest.raises(ValueError):
            crashing_task()

    assert rmock.call_count == 2
    assert rmock.request_history[0].url == RUN_LINK
    assert rmock.request_history[1].url == FAIL_LINK


def test_cronitor_does_nothing_if_cronitor_not_enabled(notify_api, rmock):
    with set_config_values(notify_api, {
        'CRONITOR_ENABLED': False,
        'CRONITOR_KEYS': {'hello': 'secret'}
    }):
        assert successful_task() == 1

    assert rmock.called is False


def test_cronitor_does_nothing_if_name_not_recognised(notify_api, rmock, caplog):
    with set_config_values(notify_api, {
        'CRONITOR_ENABLED': True,
        'CRONITOR_KEYS': {'not-hello': 'other'}
    }):
        assert successful_task() == 1

    error_log = caplog.records[0]
    assert error_log.levelname == 'ERROR'
    assert error_log.msg == 'Cronitor enabled but task_name hello not found in environment'
    assert rmock.called is False


def test_cronitor_doesnt_crash_if_request_fails(notify_api, rmock):
    rmock.get(RUN_LINK, exc=requests.exceptions.ConnectTimeout)
    rmock.get(COMPLETE_LINK, status_code=500)

    with set_config_values(notify_api, {
        'CRONITOR_ENABLED': True,
        'CRONITOR_KEYS': {'hello': 'secret'}
    }):
        assert successful_task() == 1

    assert rmock.call_count == 2
