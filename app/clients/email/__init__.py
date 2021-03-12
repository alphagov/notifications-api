from app.clients import Client, ClientException


class EmailClientException(ClientException):
    '''
    Base Exception for EmailClients
    '''
    pass


class EmailClientNonRetryableException(ClientException):
    '''
    Represents an error returned from the email client API with a 4xx response code
    that should not be retried and should instead be marked as technical failure.
    An example of this would be an email address that makes it through our
    validation rules but is rejected by SES. There is no point in retrying this type as
    it will always fail however many calls to SES. Whereas a throttling error would not
    use this exception as it may succeed if we retry
    '''
    pass


class EmailClient(Client):
    '''
    Base Email client for sending emails.
    '''

    def send_email(self, *args, **kwargs):
        raise NotImplementedError('TODO Need to implement.')

    def get_name(self):
        raise NotImplementedError('TODO Need to implement.')
