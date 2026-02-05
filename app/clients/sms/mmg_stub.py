import json
from time import monotonic

import requests
from flask import current_app

from app.clients.sms import SmsClient, SmsClientResponseException


class MMGStubClientException(SmsClientResponseException):
    pass


class MMGStubClient(SmsClient):
    """
    MMG "stub" SMS client for sending SMS to a testing stub.

    This class is not thread-safe.
    """

    name = "mmg-stub"

    def __init__(self, current_app, statsd_client, stub_url):
        super().__init__(current_app, statsd_client)
        self.url = stub_url
        self.requests_session = requests.Session()

    def try_send_sms(self, to, content, reference, international, sender):
        """
        Send SMS to the MMG stub endpoint.
        """
        data = {
            "sender": sender,
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
                if "reference" not in response_json:
                    raise ValueError("Expected 'reference' in response")
            except (ValueError, AttributeError, KeyError) as e:
                raise MMGStubClientException("Invalid response JSON from stub") from e

        except Exception as e:
            self.statsd_client.incr("clients.mmg_stub.error")
            raise MMGStubClientException(str(e)) from e
        else:
            elapsed_time = monotonic() - start_time
            current_app.logger.info(
                "MMG stub request finished in %.4g seconds", elapsed_time, {"duration": elapsed_time}
            )
            self.statsd_client.timing("clients.mmg_stub.request-time", elapsed_time)
            self.statsd_client.incr("clients.mmg_stub.success")
