import requests

from app.clients import ClientException


class MailboxException(ClientException):
    pass


class MailboxRetryableException(MailboxException):
    pass


class MailboxNonRetryableException(MailboxException):
    pass


class MailboxClient:
    """
    Mailbox message client.

    This class is not thread-safe.
    """

    name = "mailbox"

    def __init__(self, current_app):
        self.current_app = current_app
        self.api_key = current_app.config.get("MAILBOX_API_KEY")
        self.base_url = current_app.config.get("MAILBOX_BASE_URL")
        self.requests_session = requests.Session()

    def send_mailbox_message(self, subject, body, department_person_id="TEST-CITIZEN-001"):
        try:
            response = self.requests_session.post(
                f"{self.base_url}/messages",
                headers={"x-api-key": self.api_key, "x-department-id": "notify"},
                json={"departmentPersonId": department_person_id, "subject": subject, "body": body},
            )

            response.raise_for_status()
        except requests.Timeout as e:
            raise MailboxRetryableException from e
        except requests.HTTPError as e:
            if e.response.status_code == 429 or e.response.status_code >= 500:
                raise MailboxRetryableException(f"Received {e.response.status_code} from {e.request.url}") from e
            else:
                raise MailboxNonRetryableException(f"Received {e.response.status_code} from {e.request.url}") from e

        return response.json()["messageId"]
