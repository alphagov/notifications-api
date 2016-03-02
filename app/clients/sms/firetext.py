import logging
from monotonic import monotonic
from app.clients.sms import (
    SmsClient,
    SmsClientException
)
from flask import current_app
from requests import request, RequestException, HTTPError

logger = logging.getLogger(__name__)


class FiretextClientException(SmsClientException):
    pass


class FiretextClient(SmsClient):
    '''
    FireText sms client.
    '''

    def init_app(self, config, *args, **kwargs):
        super(SmsClient, self).__init__(*args, **kwargs)
        self.api_key = config.config.get('FIRETEXT_API_KEY')
        self.from_number = config.config.get('FIRETEXT_NUMBER')
        self.name = 'firetext'

    def get_name(self):
        return self.name

    def send_sms(self, to, content):

        data = {
            "apiKey": self.api_key,
            "from": self.from_number,
            "to": to.replace('+', ''),
            "message": content
        }

        try:
            start_time = monotonic()
            response = request(
                "POST",
                "https://www.firetext.co.uk/api/sendsms",
                data=data
            )
            response.raise_for_status()
        except RequestException as e:
            api_error = HTTPError.create(e)
            logger.error(
                "API {} request on {} failed with {} '{}'".format(
                    "POST",
                    "https://www.firetext.co.uk/api/sendsms",
                    api_error.status_code,
                    api_error.message
                )
            )
            raise api_error
        finally:
            elapsed_time = monotonic() - start_time
            current_app.logger.info("Firetext request finished in {}".format(elapsed_time))
        return response
