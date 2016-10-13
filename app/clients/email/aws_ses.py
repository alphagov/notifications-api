import boto3
import botocore
from flask import current_app
from monotonic import monotonic
from notifications_utils.recipients import InvalidEmailError

from app.clients import STATISTICS_DELIVERED, STATISTICS_FAILURE
from app.clients.email import (EmailClientException, EmailClient)

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
                   reply_to_address=None):
        try:
            if isinstance(to_addresses, str):
                to_addresses = [to_addresses]

            reply_to_addresses = [reply_to_address] if reply_to_address else []

            body = {
                'Text': {'Data': body}
            }

            if html_body:
                body.update({
                    'Html': {'Data': html_body}
                })

            start_time = monotonic()
            response = self._client.send_email(
                Source=source,
                Destination={
                    'ToAddresses': to_addresses,
                    'CcAddresses': [],
                    'BccAddresses': []
                },
                Message={
                    'Subject': {
                        'Data': subject,
                    },
                    'Body': body
                },
                ReplyToAddresses=reply_to_addresses
            )
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidParameterValue':
                raise InvalidEmailError('email: "{}" message: "{}"'.format(
                    to_addresses[0],
                    e.response['Error']['Message']
                ))
        except Exception as e:
            self.statsd_client.incr("clients.ses.error")
            raise AwsSesClientException(str(e))
        else:
            elapsed_time = monotonic() - start_time
            current_app.logger.info("AWS SES request finished in {}".format(elapsed_time))
            self.statsd_client.timing("clients.ses.request-time", elapsed_time)
            self.statsd_client.incr("clients.ses.success")
            return response['MessageId']
