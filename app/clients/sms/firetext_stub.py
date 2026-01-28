import json
from time import monotonic

import requests
from flask import current_app

from app.clients.sms import SmsClient, SmsClientResponseException


class FiretextStubClientException(SmsClientResponseException):
    pass


class FiretextStubClient(SmsClient):
    """
    Firetext "stub" SMS client for sending SMS to a testing stub.

    This class is not thread-safe.
    """

    name = "firetext-stub"

    def __init__(self, current_app, statsd_client, stub_url):
        super().__init__(current_app, statsd_client)
        self.url = stub_url
        self.requests_session = requests.Session()

    def try_send_sms(self, to, content, reference, international, sender):
        """
        Send SMS to the Firetext stub endpoint.
        """
        data = {
            "from": sender,
            "to": to,
            "message": content,
            "reference": reference,
        }

        try:
            start_time = monotonic()
            response = self.requests_session.request("POST", self.url, data=data, timeout=60)
            response.raise_for_status()

            try:
                response_json = json.loads(response.text)
                if response_json.get("code") != 0:
                    raise ValueError("Expected 'code' to be '0'")
            except (ValueError, AttributeError, KeyError) as e:
                raise FiretextStubClientException("Invalid response JSON from stub") from e

        except Exception as e:
            self.statsd_client.incr("clients.firetext_stub.error")
            raise FiretextStubClientException(str(e)) from e
        else:
            elapsed_time = monotonic() - start_time
            current_app.logger.info(
                "Firetext stub request finished in %.4g seconds", elapsed_time, {"duration": elapsed_time}
            )
            self.statsd_client.timing("clients.firetext_stub.request-time", elapsed_time)
            self.statsd_client.incr("clients.firetext_stub.success")
