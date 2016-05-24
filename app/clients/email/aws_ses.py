import boto3
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from monotonic import monotonic
from app.clients import STATISTICS_DELIVERED, STATISTICS_FAILURE
from app.clients.email import (EmailClientException, EmailClient)


logger = logging.getLogger(__name__)


ses_response_map = {
    'Permanent': {
        "message": 'Hard bounced',
        "success": False,
        "notification_status": 'permanent-failure',
        "notification_statistics_status": STATISTICS_FAILURE
    },
    'Temporary': {
        "message": 'Soft bounced',
        "success": False,
        "notification_status": 'temporary-failure',
        "notification_statistics_status": STATISTICS_FAILURE
    },
    'Delivery': {
        "message": 'Delivered',
        "success": True,
        "notification_status": 'delivered',
        "notification_statistics_status": STATISTICS_DELIVERED
    },
    'Complaint': {
        "message": 'Complaint',
        "success": True,
        "notification_status": 'delivered',
        "notification_statistics_status": STATISTICS_DELIVERED
    }
}


def get_aws_responses(status):
    return ses_response_map[status]


class AwsSesClientException(EmailClientException):
    pass


class AwsSesClient(EmailClient):
    '''
    Amazon SES email client.
    '''

    def init_app(self, region, statsd_client, *args, **kwargs):
        self._client = boto3.client('ses', region_name=region)
        super(AwsSesClient, self).__init__(*args, **kwargs)
        self.name = 'ses'
        self.statsd_client = statsd_client

    def get_name(self):
        return self.name

    def send_email(self,
                   source,
                   to_addresses,
                   subject,
                   body,
                   html_body='',
                   reply_to_addresses=None,
                   headers=None):
        try:
            if isinstance(to_addresses, str):
                to_addresses = [to_addresses]
            if reply_to_addresses and isinstance(reply_to_addresses, str):
                reply_to_addresses = [reply_to_addresses]
            elif reply_to_addresses is None:
                reply_to_addresses = []

            start_time = monotonic()

            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = source
            msg['To'] = ','.join(to_addresses)
            msg['ReplyToAddresses'] = ','.join(reply_to_addresses)
            msg.attach(MIMEText(body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            for k, v in headers.items():
                msg.add_header(k, v)

            response = self._client.send_raw_email(
                Source=msg['From'],
                Destinations=to_addresses,
                RawMessage={
                    'Data': msg.as_bytes()
                }
            )

            elapsed_time = monotonic() - start_time
            current_app.logger.info("AWS SES request finished in {}".format(elapsed_time))
            self.statsd_client.timing("notifications.clients.ses.request-time", elapsed_time)
            return response['MessageId']
        except Exception as e:
            logger.exception(e)
            self.statsd_client.incr("notifications.clients.ses.error")
            raise AwsSesClientException(str(e))
