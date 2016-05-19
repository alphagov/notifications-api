import json
from flask import current_app
from monotonic import monotonic
from requests import (request, RequestException, HTTPError)
from app.clients import (STATISTICS_DELIVERED, STATISTICS_FAILURE)
from app.clients.sms import (SmsClient, SmsClientException)

mmg_response_map = {
    '2': {
        "message": ' Temporary failure',
        "notification_statistics_status": STATISTICS_FAILURE,
        "success": False,
        "notification_status": 'temporary-failure'
    },
    '3': {
        "message": 'Delivered',
        "notification_statistics_status": STATISTICS_DELIVERED,
        "success": True,
        "notification_status": 'delivered'
    },
    '4': {
        "message": ' Temporary failure',
        "notification_statistics_status": STATISTICS_FAILURE,
        "success": False,
        "notification_status": 'temporary-failure'
    },
    '5': {
        "message": 'Permanent failure',
        "notification_statistics_status": STATISTICS_FAILURE,
        "success": False,
        "notification_status": 'permanent-failure'
    },
    'default': {
        "message": 'Declined',
        "success": False,
        "notification_statistics_status": STATISTICS_FAILURE,
        "notification_status": 'failed'
    }
}


def get_mmg_responses(status):
    return mmg_response_map.get(status, mmg_response_map.get('default'))


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

    def init_app(self, config, statsd_client, *args, **kwargs):
        super(SmsClient, self).__init__(*args, **kwargs)
        self.api_key = config.get('MMG_API_KEY')
        self.from_number = config.get('MMG_FROM_NUMBER')
        self.name = 'mmg'
        self.statsd_client = statsd_client

    def get_name(self):
        return self.name

    def send_sms(self, to, content, reference, multi=True):
        data = {
            "reqType": "BULK",
            "MSISDN": to,
            "msg": content,
            "sender": self.from_number,
            "cid": reference,
            "multi": multi
        }

        start_time = monotonic()
        try:
            response = request("POST", "https://www.mmgrp.co.uk/API/json/api.php",
                               data=json.dumps(data),
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Basic {}'.format(self.api_key)})
            if response.status_code != 200:
                error = response.text
                raise MMGClientException(json.loads(error))
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
            self.statsd_client.incr("notifications.clients.mmg.error")
            raise api_error
        finally:
            elapsed_time = monotonic() - start_time
            self.statsd_client.timing("notifications.clients.mmg.request-time", elapsed_time)
            current_app.logger.info("MMG request finished in {}".format(elapsed_time))
        return response
