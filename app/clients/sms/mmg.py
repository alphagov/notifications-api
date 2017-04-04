import json
from monotonic import monotonic
from requests import (request, RequestException)
from requests.exceptions import HTTPError
from app.clients import (STATISTICS_DELIVERED, STATISTICS_FAILURE)
from app.clients.sms import (SmsClient, SmsClientResponseException)

mmg_response_map = {
    '2': {
        "message": ' Permanent failure',
        "notification_statistics_status": STATISTICS_FAILURE,
        "success": False,
        "notification_status": 'permanent-failure'
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


class MMGClientResponseException(SmsClientResponseException):
    def __init__(self, response, exception):
        self.status_code = response.status_code
        self.text = response.text
        self.exception = exception

    def __str__(self):
        return "Code {} text {} exception {}".format(self.status_code, self.text, str(self.exception))


class MMGClient(SmsClient):
    '''
    MMG sms client
    '''

    def init_app(self, current_app, statsd_client, *args, **kwargs):
        super(SmsClient, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self.api_key = current_app.config.get('MMG_API_KEY')
        self.from_number = current_app.config.get('FROM_NUMBER')
        self.name = 'mmg'
        self.statsd_client = statsd_client
        self.mmg_url = current_app.config.get('MMG_URL')

    def record_outcome(self, success, response):
        log_message = "API {} request {} on {} response status_code {}".format(
            "POST",
            "succeeded" if success else "failed",
            self.mmg_url,
            response.status_code
        )

        if success:
            self.current_app.logger.info(log_message)
            self.statsd_client.incr("clients.mmg.success")
        else:
            self.statsd_client.incr("clients.mmg.error")
            self.current_app.logger.error(log_message)

    def get_name(self):
        return self.name

    def send_sms(self, to, content, reference, multi=True, sender=None):
        data = {
            "reqType": "BULK",
            "MSISDN": to,
            "msg": content,
            "sender": self.from_number if sender is None else sender,
            "cid": reference,
            "multi": multi
        }

        start_time = monotonic()
        try:
            response = request(
                "POST",
                self.mmg_url,
                data=json.dumps(data),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Basic {}'.format(self.api_key)
                },
                timeout=60
            )

            response.raise_for_status()
            try:
                json.loads(response.text)
            except (ValueError, AttributeError) as e:
                self.record_outcome(False, response)
                raise MMGClientResponseException(response=response, exception=e)
            self.record_outcome(True, response)
        except RequestException as e:
            self.record_outcome(False, e.response)
            raise MMGClientResponseException(response=e.response, exception=e)
        except HTTPError as e:
            self.record_outcome(False, e.response)
            raise MMGClientResponseException(response=e.response, exception=e)
        finally:
            elapsed_time = monotonic() - start_time
            self.statsd_client.timing("clients.mmg.request-time", elapsed_time)
            self.current_app.logger.info("MMG request for {} finished in {}".format(reference, elapsed_time))

        return response
