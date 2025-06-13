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

    def __init__(self, region, stub_url, statsd_client, otel_client):
        super().__init__()
        self.statsd_client = statsd_client
        self.otel_client = otel_client
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
            self.otel_client.incr(
                "clients_error",
                attributes={"provider": self.name},
                description="Count of failed requests to provider",
            )
            raise AwsSesStubClientException(str(e)) from e
        else:
            elapsed_time = monotonic() - start_time
            current_app.logger.info("AWS SES stub request finished in %s", elapsed_time)
            self.statsd_client.timing("clients.ses_stub.request-time", elapsed_time)
            self.statsd_client.incr("clients.ses_stub.success")
            self.otel_client.record(
                "clients_request_time",
                value=elapsed_time,
                attributes={"provider": self.name},
                description="Time taken for requests provider",
            )
            self.otel_client.incr(
                "clients_success",
                attributes={"provider": self.name},
                description="Count of successful requests to provider",
            )
            return response_json["MessageId"]
