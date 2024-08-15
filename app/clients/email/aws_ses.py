from time import monotonic

import boto3
import botocore
from flask import current_app

from app.clients import STATISTICS_DELIVERED, STATISTICS_FAILURE
from app.clients.email import (
    EmailClient,
    EmailClientException,
    EmailClientNonRetryableException,
)

ses_response_map = {
    "Permanent": {
        "message": "Hard bounced",
        "success": False,
        "notification_status": "permanent-failure",
        "notification_statistics_status": STATISTICS_FAILURE,
    },
    "Temporary": {
        "message": "Soft bounced",
        "success": False,
        "notification_status": "temporary-failure",
        "notification_statistics_status": STATISTICS_FAILURE,
    },
    "Delivery": {
        "message": "Delivered",
        "success": True,
        "notification_status": "delivered",
        "notification_statistics_status": STATISTICS_DELIVERED,
    },
    "Complaint": {
        "message": "Complaint",
        "success": True,
        "notification_status": "delivered",
        "notification_statistics_status": STATISTICS_DELIVERED,
    },
}


def get_aws_responses(status):
    return ses_response_map[status]


class AwsSesClientException(EmailClientException):
    pass


class AwsSesClientThrottlingSendRateException(AwsSesClientException):
    pass


class AwsSesClient(EmailClient):
    """
    Amazon SES email client.
    """

    def __init__(self, region, statsd_client):
        super().__init__()
        self._client = boto3.client("sesv2", region_name=region)
        self.statsd_client = statsd_client

    @property
    def name(self):
        return "ses"

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
        reply_to_addresses = [punycode_encode_email(reply_to_address)] if reply_to_address else []
        to_addresses = [punycode_encode_email(to_address)]

        body = {"Text": {"Data": body}, "Html": {"Data": html_body}}

        start_time = monotonic()

        try:
            response = self._client.send_email(
                FromEmailAddress=from_address,
                Destination={
                    "ToAddresses": to_addresses,
                    "CcAddresses": [],
                    "BccAddresses": [],
                },
                Content={
                    "Simple": {
                        "Subject": {"Data": subject},
                        "Body": body,
                        "Headers": headers,
                    },
                },
                ReplyToAddresses=reply_to_addresses,
            )
        except botocore.exceptions.ClientError as e:
            self.statsd_client.incr("clients.ses.error")

            # http://docs.aws.amazon.com/ses/latest/DeveloperGuide/api-error-codes.html
            if e.response["Error"]["Code"] == "InvalidParameterValue":
                raise EmailClientNonRetryableException(e.response["Error"]["Message"]) from e
            elif (
                e.response["Error"]["Code"] == "Throttling"
                and e.response["Error"]["Message"] == "Maximum sending rate exceeded."
            ):
                raise AwsSesClientThrottlingSendRateException(str(e)) from e
            else:
                self.statsd_client.incr("clients.ses.error")
                raise AwsSesClientException(str(e)) from e
        except Exception as e:
            self.statsd_client.incr("clients.ses.error")
            raise AwsSesClientException(str(e)) from e
        else:
            elapsed_time = monotonic() - start_time
            current_app.logger.info(
                "AWS SES request finished in %s",
                elapsed_time,
                extra={
                    "elapsed_time": elapsed_time,
                },
            )
            self.statsd_client.timing("clients.ses.request-time", elapsed_time)
            self.statsd_client.incr("clients.ses.success")
            return response["MessageId"]


def punycode_encode_email(email_address):
    # only the hostname should ever be punycode encoded.
    local, hostname = email_address.split("@")
    return "{}@{}".format(local, hostname.encode("idna").decode("utf-8"))
