import json
from time import monotonic

import requests
from flask import current_app

from app.clients.email import EmailClient, EmailClientException


class AwsSesStubClientException(EmailClientException):
    pass


class AwsSesStubClient(EmailClient):
    """
    Amazon SES "stub" email client for sending emails to a testing stub.

    This class is not thread-safe.
    """

    name = "ses"

    def __init__(self, region, statsd_client, stub_url):
        super().__init__()
        self.statsd_client = statsd_client
        self.url = stub_url
        self.requests_session = requests.Session()

    def send_email(
        self,
        *,
        from_address: str,
        to_address: str,
        subject: str,
        body: str,
        html_body: str,
        reply_to_address: str | None,
        headers: list[dict[str, str]],
    ) -> str:
        try:
            start_time = monotonic()
            response = self.requests_session.request("POST", self.url, data={"id": "dummy-data"}, timeout=60)
            response.raise_for_status()
            response_json = json.loads(response.text)

        except Exception as e:
            self.statsd_client.incr("clients.ses_stub.error")
            raise AwsSesStubClientException(str(e)) from e
        else:
            elapsed_time = monotonic() - start_time
            current_app.logger.info("AWS SES stub request finished in %s", elapsed_time)
            self.statsd_client.timing("clients.ses_stub.request-time", elapsed_time)
            self.statsd_client.incr("clients.ses_stub.success")
            return response_json["MessageId"]
