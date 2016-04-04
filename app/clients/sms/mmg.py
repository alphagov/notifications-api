from flask import current_app
from monotonic import monotonic
from requests import (request, RequestException, HTTPError)

from app.clients import (ClientResponse, STATISTICS_DELIVERED, STATISTICS_FAILURE)
from app.clients.sms import (SmsClient, SmsClientException)


class FiretextResponses(ClientResponse):
    def __init__(self):
        ClientResponse.__init__(self)
        self.__response_model__ = {
            '0': {
                "message": 'Delivered',
                "notification_statistics_status": STATISTICS_DELIVERED,
                "success": True,
                "notification_status": 'delivered'
            },
            '1': {
                "message": 'Declined',
                "success": False,
                "notification_statistics_status": STATISTICS_FAILURE,
                "notification_status": 'failed'
            },
            '2': {
                "message": 'Undelivered (Pending with Network)',
                "success": False,
                "notification_statistics_status": None,
                "notification_status": 'sent'
            }
        }



class MMGClientException(SmsClientException):
    def __init__(self, error_response):
        self.code = error_response['Error']
        self.description = error_response['Description']

    def __str__(self):
        return "Code {} description {}".format(self.code, self.description)


class MMGClient(SmsClient):
    '''
    MMG sms client
    '''

    def init_app(self, config, *args, **kwargs):
        super(SmsClient, self).__init__(*args, *kwargs)
        self.api_key = config.get('MMG_API_KEY')
        self.from_number = config.get('NOTIFY_FROM_NUMBER')
        self.name = 'mmg'

    def get_name(self):
        return self.name

    def send_sms(self, to, content, reference):
        data = {
            "reqType": "BULK",
            "MSISDN": to,
            "msg": content,
            "sender": self.from_number
        }

        start_time = monotonic()
        try:
            response = request("POST", "https://www.mmgrp.co.uk/API/json/api.php",
                               data=data)
            if response.status_code != 200:
                error = response.json
                raise MMGClientException(error)
            response.raise_for_status()
        except RequestException as e:
            api_error = HTTPError.create(e)
            current_app.logger.error(
                "API {} request on {} failed with {} '{}'".format(
                    "POST",
                    "https://www.mmgrp.co.uk/API/json/api.php",
                    api_error.status_code,
                    api_error.message
                )
            )
            raise api_error
        finally:
            elapsed_time = monotonic() - start_time
            current_app.logger.info("MMG request finished in {}".format(elapsed_time))
        return response
