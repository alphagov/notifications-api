import logging
from monotonic import monotonic
from app.clients.sms import (
    SmsClient,
    SmsClientException
)
from flask import current_app
from requests import request, RequestException, HTTPError

logger = logging.getLogger(__name__)

firetext_response_status = {
    '0': {
        "firetext_message": 'delivered',
        "success": True,
        "notify_status": 'delivered'
    },
    '1': {
        "firetext_message": 'declined',
        "success": False,
        "notify_status": 'failed'
    },
    '2': {
        "firetext_message": 'Undelivered (Pending with Network)',
        "success": False,
        "notify_status": 'sent'
    }
}


class FiretextClientException(SmsClientException):
    def __init__(self, response):
        self.code = response['code']
        self.description = response['description']

    def __str__(self):
        return "Code {} description {}".format(self.code, self.description)


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

    def send_sms(self, to, content, notification_id=None):

        data = {
            "apiKey": self.api_key,
            "from": self.from_number,
            "to": to.replace('+', ''),
            "message": content
        }

        if notification_id:
            data.update({
                "reference": notification_id
            })

        start_time = monotonic()
        try:
            response = request(
                "POST",
                "https://www.firetext.co.uk/api/sendsms/json",
                data=data
            )
            firetext_response = response.json()
            if firetext_response['code'] != 0:
                raise FiretextClientException(firetext_response)
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
