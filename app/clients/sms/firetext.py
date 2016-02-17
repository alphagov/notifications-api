import logging
from app.clients.sms import (
    SmsClient,
    SmsClientException
)
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
        print(config.config)
        self.api_key = config.config.get('FIRETEXT_API_KEY')
        self.from_number = config.config.get('FIRETEXT_NUMBER')

    def send_sms(self, to, content):

        data = {
            "apiKey": self.api_key,
            "from": self.from_number,
            "to": to.replace('+', ''),
            "message": content
        }

        print(data)

        try:
            response = request(
                "POST",
                "https://www.firetext.co.uk/api/sendsms",
                data=data
            )
            response.raise_for_status()
        except RequestException as e:
            api_error = HTTPError.create(e)
            print(
                "API {} request on {} failed with {} '{}'".format(
                    "POST",
                    "https://www.firetext.co.uk/api/sendsms",
                    api_error.status_code,
                    api_error.message
                )
            )
            raise api_error
        return response
