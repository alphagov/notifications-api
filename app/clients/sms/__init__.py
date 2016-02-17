from app.clients import (Client, ClientException)


class SmsClientException(ClientException):
    '''
    Base Exception for SmsClients
    '''
    pass


class SmsClient(Client):
    '''
    Base Sms client for sending smss.
    '''

    def send_sms(self, *args, **kwargs):
        raise NotImplemented('TODO Need to implement.')
