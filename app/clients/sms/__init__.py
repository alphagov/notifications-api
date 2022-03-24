from app.clients import Client, ClientException


class SmsClientResponseException(ClientException):
    '''
    Base Exception for SmsClientsResponses
    '''

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return "Message {}".format(self.message)


class SmsClient(Client):
    '''
    Base Sms client for sending smss.
    '''

    def record_outcome(self, success):
        log_message = "Provider request for {} {}".format(
            self.name,
            "succeeded" if success else "failed",
        )

        if success:
            self.current_app.logger.info(log_message)
            self.statsd_client.incr(f"clients.{self.name}.success")
        else:
            self.statsd_client.incr(f"clients.{self.name}.error")
            self.current_app.logger.warning(log_message)

    def send_sms(self, *args, **kwargs):
        raise NotImplementedError('TODO Need to implement.')

    @property
    def name(self):
        raise NotImplementedError('TODO Need to implement.')
