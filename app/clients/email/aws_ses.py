import boto3

from app.clients.email import (EmailClientException, EmailClient)


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
                   reply_to_addresses=None):
        try:
            if isinstance(to_addresses, str):
                to_addresses = [to_addresses]
            if reply_to_addresses and isinstance(reply_to_addresses, str):
                reply_to_addresses = [reply_to_addresses]
            elif reply_to_addresses is None:
                reply_to_addresses = []

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
                    'Body': {
                        'Text': {
                            'Data': body}}
                },
                ReplyToAddresses=reply_to_addresses)
            return response['MessageId']
        except Exception as e:
            # TODO logging exceptions
            raise AwsSesClientException(str(e))
