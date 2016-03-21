import boto3
from flask import current_app
from monotonic import monotonic
from app.clients import ClientResponse, STATISTICS_DELIVERED, STATISTICS_FAILURE
from app.clients.email import (EmailClientException, EmailClient)


class AwsSesResponses(ClientResponse):
    def __init__(self):
        ClientResponse.__init__(self)
        self.__response_model__ = {
            'Bounce': {
                "message": 'Bounced',
                "success": False,
                "notification_status": 'bounce',
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
                "success": False,
                "notification_status": 'complaint',
                "notification_statistics_status": STATISTICS_FAILURE
            }
        }


class AwsSesClientException(EmailClientException):
    pass


class AwsSesClient(EmailClient):
    '''
    Amazon SES email client.
    '''

    def init_app(self, region, *args, **kwargs):
        self._client = boto3.client('ses', region_name=region)
        super(AwsSesClient, self).__init__(*args, **kwargs)
        self.name = 'ses'

    def get_name(self):
        return self.name

    def send_email(self,
                   source,
                   to_addresses,
                   subject,
                   body,
                   html_body='',
                   reply_to_addresses=None):
        try:
            if isinstance(to_addresses, str):
                to_addresses = [to_addresses]
            if reply_to_addresses and isinstance(reply_to_addresses, str):
                reply_to_addresses = [reply_to_addresses]
            elif reply_to_addresses is None:
                reply_to_addresses = []

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
                ReplyToAddresses=reply_to_addresses)
            elapsed_time = monotonic() - start_time
            current_app.logger.info("AWS SES request finished in {}".format(elapsed_time))
            return response['MessageId']
        except Exception as e:
            # TODO logging exceptions
            raise AwsSesClientException(str(e))
