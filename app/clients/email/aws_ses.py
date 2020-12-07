import boto3
import botocore
from flask import current_app
from time import monotonic
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


class AwsSesClientThrottlingSendRateException(AwsSesClientException):
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

        # events are generally undocumented, but some that might be of interest are:
        # before-call, after-call, after-call-error, request-created, response-received
        self._client.meta.events.register('request-created.ses.SendEmail', self.ses_request_created_hook)
        self._client.meta.events.register('response-received.ses.SendEmail', self.ses_response_received_hook)

    def ses_request_created_hook(self, **kwargs):
        # request created may be called multiple times if the request auto-retries. We want to count all these as the
        # same request for timing purposes, so only reset the start time if it was cleared completely
        if self.ses_start_time == 0:
            self.ses_start_time = monotonic()

    def ses_response_received_hook(self, **kwargs):
        # response received may be called multiple times if the request auto-retries, however, we want to count the last
        # time it triggers for timing purposes, so always reset the elapsed time
        self.ses_elapsed_time = monotonic() - self.ses_start_time

    def get_name(self):
        return self.name

    def send_email(self,
                   source,
                   to_addresses,
                   subject,
                   body,
                   html_body='',
                   reply_to_address=None):
        self.ses_elapsed_time = 0
        self.ses_start_time = 0
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
                    'ToAddresses': [punycode_encode_email(addr) for addr in to_addresses],
                    'CcAddresses': [],
                    'BccAddresses': []
                },
                Message={
                    'Subject': {
                        'Data': subject,
                    },
                    'Body': body
                },
                ReplyToAddresses=[punycode_encode_email(addr) for addr in reply_to_addresses]
            )
        except botocore.exceptions.ClientError as e:
            self.statsd_client.incr("clients.ses.error")

            # http://docs.aws.amazon.com/ses/latest/DeveloperGuide/api-error-codes.html
            if e.response['Error']['Code'] == 'InvalidParameterValue':
                raise InvalidEmailError('email: "{}" message: "{}"'.format(
                    to_addresses[0],
                    e.response['Error']['Message']
                ))
            elif (
                e.response['Error']['Code'] == 'Throttling'
                and e.response['Error']['Message'] == 'Maximum sending rate exceeded.'
            ):
                raise AwsSesClientThrottlingSendRateException(str(e))
            else:
                self.statsd_client.incr("clients.ses.error")
                raise AwsSesClientException(str(e))
        except Exception as e:
            self.statsd_client.incr("clients.ses.error")
            raise AwsSesClientException(str(e))
        else:
            elapsed_time = monotonic() - start_time
            current_app.logger.info("AWS SES request finished in {}".format(elapsed_time))
            self.statsd_client.timing("clients.ses.request-time", elapsed_time)
            if self.ses_elapsed_time != 0:
                self.statsd_client.timing("clients.ses.raw-request-time", self.ses_elapsed_time)
            self.statsd_client.incr("clients.ses.success")
            return response['MessageId']


def punycode_encode_email(email_address):
    # only the hostname should ever be punycode encoded.
    local, hostname = email_address.split('@')
    return '{}@{}'.format(local, hostname.encode('idna').decode('utf-8'))
