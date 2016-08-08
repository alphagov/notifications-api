from mock import ANY

from app.statsd_decorators import statsd
import app


class AnyStringWith(str):
    def __eq__(self, other):
        return self in other


def test_should_call_statsd(notify_api, mocker):
    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing')
    mock_logger = mocker.patch.object(notify_api.logger, 'info')

    @statsd(namespace="test")
    def test_function():
        return True

    assert test_function()
    app.statsd_client.incr.assert_called_once_with("test.test_function")
    app.statsd_client.timing.assert_called_once_with("test.test_function", ANY)
    mock_logger.assert_called_once_with(AnyStringWith("test call test_function took "))
