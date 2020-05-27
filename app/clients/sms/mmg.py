import json
from time import monotonic
from requests import (request, RequestException)
from app.clients.sms import (SmsClient, SmsClientResponseException)

mmg_response_map = {
    '2': {'status': 'permanent-failure', 'substatus': {
        "1": "Number does not exist",
        "4": "Rejected by operator",
        "5": "Unidentified Subscriber",
        "9": "Undelivered",
        "11": "Service for Subscriber suspended",
        "12": "Illegal equipment",
        "2049": "Subscriber IMSI blacklisted",
        "2050": "Number blacklisted in do-not-disturb blacklist",
        "2052": "Destination number blacklisted",
        "2053": "Source address blacklisted"
    }},
    '3': {'status': 'delivered', 'substatus': {"2": "Delivered to operator", "5": "Delivered to handset"}},
    '4': {'status': 'temporary-failure', 'substatus': {
        "6": "Absent Subscriber",
        "8": "Roaming not allowed",
        "13": "SMS Not Supported",
        "15": "Expired",
        "27": "Absent Subscriber",
        "29": "Invalid delivery report",
        "32": "Delivery Failure",
    }},
    '5': {'status': 'permanent-failure', 'substatus': {
        "6": "Network out of coverage",
        "8": "Incorrect number prefix",
        "10": "Number on do-not-disturb service",
        "11": "Sender id not registered",
        "13": "Sender id blacklisted",
        "14": "Destination number blacklisted",
        "19": "Routing unavailable",
        "20": "Rejected by anti-flooding mechanism",
        "21": "System error",  # it says to retry those messages or contact support
        "23": "Duplicate message id",
        "24": "Message formatted incorrectly",
        "25": "Message too long",
        "51": "Missing recipient value",
        "52": "Invalid destination",
    }},
}


def get_mmg_responses(status, substatus=None):
    return (mmg_response_map[status]["status"], mmg_response_map[status]["substatus"].get(substatus, None))


class MMGClientResponseException(SmsClientResponseException):
    def __init__(self, response, exception):
        status_code = response.status_code if response is not None else 504
        text = response.text if response is not None else "Gateway Time-out"

        self.status_code = status_code
        self.text = text
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
        status_code = response.status_code if response else 503
        log_message = "API {} request {} on {} response status_code {}".format(
            "POST",
            "succeeded" if success else "failed",
            self.mmg_url,
            status_code
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
        finally:
            elapsed_time = monotonic() - start_time
            self.statsd_client.timing("clients.mmg.request-time", elapsed_time)
            self.current_app.logger.info("MMG request for {} finished in {}".format(reference, elapsed_time))

        return response
