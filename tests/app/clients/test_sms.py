import pytest

from app import otel_client, statsd_client
from app.clients.sms import SmsClient, SmsClientResponseException


@pytest.fixture
def fake_client(notify_api):
    class FakeSmsClient(SmsClient):
        name = "fake"

        def try_send_sms(self):
            pass

    fake_client = FakeSmsClient(notify_api, statsd_client, otel_client)
    return fake_client


def test_send_sms(fake_client, mocker):
    mock_send = mocker.patch.object(fake_client, "try_send_sms")

    fake_client.send_sms(
        to="to",
        content="content",
        reference="reference",
        international=False,
        sender="testing",
    )

    mock_send.assert_called_with("to", "content", "reference", False, "testing")


def test_send_sms_error(fake_client, mocker):
    mocker.patch.object(fake_client, "try_send_sms", side_effect=SmsClientResponseException("error"))

    with pytest.raises(SmsClientResponseException):
        fake_client.send_sms(
            to="to",
            content="content",
            reference="reference",
            international=False,
            sender=None,
        )
