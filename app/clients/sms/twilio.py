from monotonic import monotonic
from app.clients.sms import (
    SmsClient, SmsClientException)
from twilio.rest import TwilioRestClient
from twilio import TwilioRestException
from flask import current_app


class TwilioClientException(SmsClientException):
    pass


class TwilioClient(SmsClient):
    '''
    Twilio sms client.
    '''
    def init_app(self, config, *args, **kwargs):
        super(TwilioClient, self).__init__(*args, **kwargs)
        self.client = TwilioRestClient(
            config.config.get('TWILIO_ACCOUNT_SID'),
            config.config.get('TWILIO_AUTH_TOKEN'))
        self.from_number = config.config.get('TWILIO_NUMBER')
        self.name = 'twilio'

    def get_name(self):
        return self.name

    def send_sms(self, to, content):
        start_time = monotonic()
        try:
            response = self.client.messages.create(
                body=content,
                to=to,
                from_=self.from_number
            )
            return response.sid
        except TwilioRestException as e:
            current_app.logger.exception(e)
            raise TwilioClientException(e)
        finally:
            elapsed_time = monotonic() - start_time
            current_app.logger.info("Twilio request finished in {}".format(elapsed_time))

    def status(self, message_id):
        try:
            response = self.client.messages.get(message_id)
            if response.status in ('delivered', 'undelivered', 'failed'):
                return response.status
            return None
        except TwilioRestException as e:
            current_app.logger.exception(e)
            raise TwilioClientException(e)
