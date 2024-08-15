import json
import logging

from requests import RequestException, request

from app.clients.sms import SmsClient, SmsClientResponseException

logger = logging.getLogger(__name__)

# Firetext will send a delivery receipt with three different status codes.
# The `firetext_response` maps these codes to the notification statistics status and notification status.
# If we get a pending (status = 2) delivery receipt followed by a declined (status = 1) delivery receipt we will set
# the notification status to temporary-failure rather than permanent failure.
#  See the code in the notification_dao.update_notifications_status_by_id
firetext_responses = {"0": "delivered", "1": "permanent-failure", "2": "pending"}

# For some extra context, see google drive: GOV.UK Notify -> SMS suppliers -> Detailed failure statuses
firetext_codes = {
    # code '000' means 'No errors reported'
    "000": {"status": "temporary-failure", "reason": "No error reported"},
    "101": {"status": "permanent-failure", "reason": "Unknown Subscriber"},
    "102": {"status": "temporary-failure", "reason": "Absent Subscriber"},
    "103": {"status": "temporary-failure", "reason": "Subscriber Busy"},
    "104": {"status": "temporary-failure", "reason": "No Subscriber Memory"},
    "201": {"status": "permanent-failure", "reason": "Invalid Number"},
    "301": {"status": "permanent-failure", "reason": "SMS Not Supported"},
    "302": {"status": "temporary-failure", "reason": "SMS Not Supported"},
    "401": {"status": "permanent-failure", "reason": "Message Rejected"},
    "900": {"status": "temporary-failure", "reason": "Routing Error"},
}


def get_firetext_responses(status, detailed_status_code=None):
    detailed_status = (
        firetext_codes[detailed_status_code]["reason"] if firetext_codes.get(detailed_status_code, None) else None
    )
    return (firetext_responses[status], detailed_status)


def get_message_status_and_reason_from_firetext_code(detailed_status_code):
    return firetext_codes[detailed_status_code]["status"], firetext_codes[detailed_status_code]["reason"]


class FiretextClient(SmsClient):
    """
    FireText sms client.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = self.current_app.config.get("FIRETEXT_API_KEY")
        self.international_api_key = self.current_app.config.get("FIRETEXT_INTERNATIONAL_API_KEY")
        self.url = self.current_app.config.get("FIRETEXT_URL")
        self.receipt_url = self.current_app.config.get("FIRETEXT_RECEIPT_URL")

    @property
    def name(self):
        return "firetext"

    def try_send_sms(self, to, content, reference, international, sender):
        data = {
            "apiKey": self.international_api_key if international else self.api_key,
            "from": sender,
            "to": to.replace("+", ""),
            "message": content,
            "reference": reference,
        }

        if self.receipt_url:
            data["receipt"] = self.receipt_url

        try:
            response = request("POST", self.url, data=data, timeout=60)
            response.raise_for_status()
            try:
                json.loads(response.text)
                if response.json()["code"] != 0:
                    raise ValueError("Expected 'code' to be '0'")
            except (ValueError, AttributeError) as e:
                raise SmsClientResponseException("Invalid response JSON") from e
        except RequestException as e:
            raise SmsClientResponseException("Request failed") from e

        return response
