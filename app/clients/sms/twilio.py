import logging
from app.clients.sms import (
    SmsClient, SmsClientException)
from twilio.rest import TwilioRestClient
from twilio import TwilioRestException


logger = logging.getLogger(__name__)


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

    def send_sms(self, to, content):
        try:
            response = self.client.messages.create(
                body=content,
                to=to,
                from_=self.from_number
            )
            return response.sid
        except TwilioRestException as e:
            logger.exception(e)
            raise TwilioClientException(e)

    def status(self, message_id):
        try:
            response = self.client.messages.get(message_id)
            if response.status in ('delivered', 'undelivered', 'failed'):
                return response.status
            return None
        except TwilioRestException as e:
            logger.exception(e)
            raise TwilioClientException(e)
