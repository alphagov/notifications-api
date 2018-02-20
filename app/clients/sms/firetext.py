import json
import logging

from monotonic import monotonic
from requests import request, RequestException

from app.clients.sms import (SmsClient, SmsClientResponseException)

logger = logging.getLogger(__name__)

# Firetext will send a delivery receipt with three different status codes.
# The `firetext_response` maps these codes to the notification statistics status and notification status.
# If we get a pending (status = 2) delivery receipt followed by a declined (status = 1) delivery receipt we will set
# the notification status to temporary-failure rather than permanent failure.
#  See the code in the notification_dao.update_notifications_status_by_id
firetext_responses = {
    '0': 'delivered',
    '1': 'permanent-failure',
    '2': 'pending'
}


def get_firetext_responses(status):
    return firetext_responses[status]


class FiretextClientResponseException(SmsClientResponseException):
    def __init__(self, response, exception):
        status_code = response.status_code if response is not None else 504
        text = response.text if response is not None else "Gateway Time-out"
        self.status_code = status_code
        self.text = text
        self.exception = exception

    def __str__(self):
        return "Code {} text {} exception {}".format(self.status_code, self.text, str(self.exception))


class FiretextClient(SmsClient):
    '''
    FireText sms client.
    '''

    def init_app(self, current_app, statsd_client, *args, **kwargs):
        super(SmsClient, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self.api_key = current_app.config.get('FIRETEXT_API_KEY')
        self.from_number = current_app.config.get('FROM_NUMBER')
        self.name = 'firetext'
        self.url = "https://www.firetext.co.uk/api/sendsms/json"
        self.statsd_client = statsd_client

    def get_name(self):
        return self.name

    def record_outcome(self, success, response):
        status_code = response.status_code if response else 503

        log_message = "API {} request {} on {} response status_code {}".format(
            "POST",
            "succeeded" if success else "failed",
            self.url,
            status_code
        )

        if success:
            self.current_app.logger.info(log_message)
            self.statsd_client.incr("clients.firetext.success")
        else:
            self.statsd_client.incr("clients.firetext.error")
            self.current_app.logger.error(log_message)

    def send_sms(self, to, content, reference, sender=None):

        data = {
            "apiKey": self.api_key,
            "from": self.from_number if sender is None else sender,
            "to": to.replace('+', ''),
            "message": content,
            "reference": reference
        }

        start_time = monotonic()
        try:
            response = request(
                "POST",
                self.url,
                data=data,
                timeout=60
            )
            response.raise_for_status()
            try:
                json.loads(response.text)
                if response.json()['code'] != 0:
                    raise ValueError()
            except (ValueError, AttributeError) as e:
                self.record_outcome(False, response)
                raise FiretextClientResponseException(response=response, exception=e)
            self.record_outcome(True, response)
        except RequestException as e:
            self.record_outcome(False, e.response)
            raise FiretextClientResponseException(response=e.response, exception=e)
        finally:
            elapsed_time = monotonic() - start_time
            self.current_app.logger.info("Firetext request for {} finished in {}".format(reference, elapsed_time))
            self.statsd_client.timing("clients.firetext.request-time", elapsed_time)
        return response
