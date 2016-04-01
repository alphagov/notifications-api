from flask import current_app
from monotonic import monotonic
from requests import request, RequestException, HTTPError
from app.clients.sms import SmsClient


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

