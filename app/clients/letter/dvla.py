import base64
import contextlib
import secrets
import string
import time
from collections.abc import Callable
from typing import Literal

import boto3
import jwt
import requests
from flask import current_app
from notifications_utils.recipient_validation.postal_address import PostalAddress
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from app.clients import ClientException
from app.constants import ECONOMY_CLASS, EUROPE, FIRST_CLASS, INTERNATIONAL_POSTAGE_TYPES, REST_OF_WORLD


class DvlaException(ClientException):
    pass


class DvlaRetryableException(DvlaException):
    pass


class DvlaNonRetryableException(DvlaException):
    pass


class DvlaDuplicatePrintRequestException(DvlaNonRetryableException):
    pass


class DvlaUnauthorisedRequestException(DvlaRetryableException):
    pass


class DvlaThrottlingException(DvlaRetryableException):
    pass


@contextlib.contextmanager
def _handle_common_dvla_errors(custom_httperror_exc_handler: Callable[[requests.HTTPError], None] = lambda x: None):
    try:
        yield
    except (ConnectionError, requests.ConnectionError, requests.Timeout) as e:
        raise DvlaRetryableException from e
    except requests.HTTPError as e:
        custom_httperror_exc_handler(e)

        if e.response.status_code == 429:
            raise DvlaThrottlingException from e
        elif e.response.status_code >= 500:
            raise DvlaRetryableException(f"Received {e.response.status_code} from {e.request.url}") from e
        else:
            raise DvlaNonRetryableException(f"Received {e.response.status_code} from {e.request.url}") from e


class SSMParameter:
    # note that if another process/app changes the value, this cache won't be automatically invalidated

    def __init__(self, key, ssm_client):
        self.key = key
        self.ssm_client = ssm_client
        self._value = None

    def get(self):
        if self._value is not None:
            return self._value
        self._value = self.ssm_client.get_parameter(Name=self.key, WithDecryption=True)["Parameter"]["Value"]
        return self._value

    def set(self, value):
        # this errors if the parameter doesn't exist yet in SSM as we haven't supplied a `Type`
        # this is fine for our purposes, as we'll always want to pre-seed this data.
        self.ssm_client.put_parameter(Name=self.key, Value=value, Overwrite=True)
        self._value = value

    def clear(self):
        self._value = None


class _SpecifiedCiphersAdapter(HTTPAdapter):
    """An HTTPAdapter for requests that will enforce specific SSL ciphers.

    If ciphers=None, no restrictions will be enforced (eg for local development).
    """

    def __init__(self, ciphers, *args, **kwargs):
        self.ciphers = ciphers
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = create_urllib3_context(ciphers=self.ciphers)
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = create_urllib3_context(ciphers=self.ciphers)
        return super().proxy_manager_for(*args, **kwargs)


class DVLAClient:
    """
    DVLA HTTP API letter client.

    This class is not thread-safe.
    """

    name = "dvla"

    statsd_client = None

    _jwt_token = None
    _jwt_expires_at = None

    def __init__(self, application, *, statsd_client):
        self.base_url = application.config["DVLA_API_BASE_URL"]
        self.ciphers = application.config["DVLA_API_TLS_CIPHERS"]
        ssm_client = boto3.client("ssm", region_name=application.config["AWS_REGION"])
        self.dvla_username = SSMParameter(key="/notify/api/dvla_username", ssm_client=ssm_client)
        self.dvla_password = SSMParameter(key="/notify/api/dvla_password", ssm_client=ssm_client)
        self.dvla_api_key = SSMParameter(key="/notify/api/dvla_api_key", ssm_client=ssm_client)
        self.statsd_client = statsd_client

        self.session = requests.Session()
        self.session.mount(self.base_url, _SpecifiedCiphersAdapter(ciphers=self.ciphers))

    @property
    def jwt_token(self):
        # if the jwt is about to expire, just reset it ourselves to avoid unnecessary 401s
        buffer = 60
        if not self._jwt_token or time.time() + buffer >= self._jwt_expires_at:
            self._jwt_token = self.authenticate()
            jwt_dict = jwt.decode(self._jwt_token, options={"verify_signature": False})
            self._jwt_expires_at = jwt_dict["exp"]

        return self._jwt_token

    def authenticate(self):
        """
        Fetch a JWT from the DVLA API that can be used in other DVLA API requests
        """

        def _handle_401(e: requests.HTTPError):
            if e.response.status_code == 401:
                # likely the old password has already expired
                current_app.logger.exception("Failed to generate a DVLA jwt token")

                self.dvla_password.clear()
                raise DvlaRetryableException(e.response.json()[0]["detail"]) from e

        with _handle_common_dvla_errors(custom_httperror_exc_handler=_handle_401):
            response = self.session.post(
                f"{self.base_url}/thirdparty-access/v1/authenticate",
                json={
                    "userName": self.dvla_username.get(),
                    "password": self.dvla_password.get(),
                },
            )
            response.raise_for_status()

        return response.json()["id-token"]

    def change_api_key(self):
        from app import redis_store

        with redis_store.get_lock(f"dvla-change-api-key-{self.dvla_username.get()}", timeout=60, blocking=False):
            # clear and re-fetch dvla api key, just to ensure we have the latest version
            self.dvla_api_key.clear()

            def _handle_401(e: requests.HTTPError):
                if e.response.status_code == 401:
                    # the api key is invalid, but we know it's current as per SSM as we fetched it at the beginning of
                    # this block. It feels most likely that the api key has just been changed by another process and
                    # DVLA's eventual consistency hasn't caught up yet. The other alternative is that the key expired
                    # due to being a year old - at which point we need to manually reset it
                    current_app.logger.exception("Failed to change DVLA api key")

                    self.dvla_api_key.clear()
                    raise DvlaNonRetryableException(e.response.json()[0]["detail"]) from e

            with _handle_common_dvla_errors(custom_httperror_exc_handler=_handle_401):
                response = self.session.post(
                    f"{self.base_url}/thirdparty-access/v1/new-api-key",
                    headers=self._get_auth_headers(),
                )
                response.raise_for_status()

            self.dvla_api_key.set(response.json()["newApiKey"])

    def change_password(self):
        from app import redis_store

        new_password = self._generate_password()

        with redis_store.get_lock(f"dvla-change-password-{self.dvla_username.get()}", timeout=60, blocking=False):
            # clear and re-fetch dvla password, just to ensure we have the latest version
            self.dvla_password.clear()

            def _handle_401(e: requests.HTTPError):
                if e.response.status_code == 401:
                    # the password is invalid, but we know it's current as per SSM as we fetched it at the beginning of
                    # this block. It feels most likely that the password has just been changed by another process and
                    # DVLA's eventual consistency hasn't caught up yet. The other alternative is that the key expired
                    # due to being 90 days old - at which point we need to manually reset it
                    current_app.logger.exception("Failed to change DVLA password")

                    self.dvla_password.clear()
                    raise DvlaNonRetryableException(e.response.json()[0]["detail"]) from e

            with _handle_common_dvla_errors(custom_httperror_exc_handler=_handle_401):
                response = self.session.post(
                    f"{self.base_url}/thirdparty-access/v1/password",
                    json={
                        "userName": self.dvla_username.get(),
                        "password": self.dvla_password.get(),
                        "newPassword": new_password,
                    },
                )
                response.raise_for_status()

            self.dvla_password.set(new_password)

    @staticmethod
    def _generate_password():
        """
        DVLA api password must be at least 8 characters in length and contain upper, lower, numerical and special
        characters.

        This function creates a valid password of length 34 characters.
        """

        password_length = 30

        alphabet = string.ascii_letters + string.digits + string.punctuation
        while range(100):
            password = "".join(secrets.choice(alphabet) for i in range(password_length))
            if (
                any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(not c.isalnum() for c in password)
            ):
                return password
        raise RuntimeError("Unable to generate sufficiently secure password")

    def _get_auth_headers(self):
        return {
            "Accept": "application/json",
            "Authorization": self.jwt_token,
            "X-API-Key": self.dvla_api_key.get(),
        }

    def send_letter(
        self,
        *,
        notification_id: str,
        reference: str,
        address: PostalAddress,
        postage: Literal["first", "second", "europe", "rest-of-world", "economy"],
        service_id: str,
        organisation_id: str,
        pdf_file: bytes,
        callback_url: str,
    ):
        """
        Sends a letter to the DVLA for printing
        """

        def _handle_http_errors(e: requests.HTTPError):
            if e.response.status_code == 400:
                raise DvlaNonRetryableException(e.response.json()["errors"][0]["detail"]) from e
            elif e.response.status_code in {401, 403}:
                # probably the api key is not valid
                self.dvla_api_key.clear()

                raise DvlaUnauthorisedRequestException(e.response.json()["errors"][0]["detail"]) from e
            elif e.response.status_code == 409:
                raise DvlaDuplicatePrintRequestException(e.response.json()["errors"][0]["detail"]) from e

        with _handle_common_dvla_errors(custom_httperror_exc_handler=_handle_http_errors):
            response = self.session.post(
                f"{self.base_url}/print-request/v1/print/jobs",
                headers=self._get_auth_headers(),
                json=self._format_create_print_job_json(
                    notification_id=notification_id,
                    reference=reference,
                    address=address,
                    postage=postage,
                    service_id=service_id,
                    organisation_id=organisation_id,
                    pdf_file=pdf_file,
                    callback_url=callback_url,
                ),
            )
            response.raise_for_status()
            return response.json()

    def _format_create_print_job_json(
        self, *, notification_id, reference, address, postage, service_id, organisation_id, pdf_file, callback_url
    ):
        # We shouldn't need to pass the postage in, as the address has a postage field. However, at this point we've
        # recorded the postage on the notification so we should respect that rather than introduce any possible
        # uncertainty from the PostalAddress resolving to something else dynamically.
        recipient, address_data = self._parse_recipient_and_address(postage=postage, address=address)

        recipient = recipient[:255]
        address_data = self._truncate_long_address_lines(address_data)

        json_payload = {
            "id": notification_id,
            "standardParams": {
                "jobType": "NOTIFY",
                "templateReference": "NOTIFY",
                "businessIdentifier": reference,
                "recipientName": recipient,
                "address": address_data,
            },
            "customParams": [
                {"key": "pdfContent", "value": base64.b64encode(pdf_file).decode("utf-8")},
                {"key": "organisationIdentifier", "value": organisation_id},
                {"key": "serviceIdentifier", "value": service_id},
            ],
        }

        json_payload["callbackParams"] = {
            "target": callback_url,
            "retryParams": {"enabled": True, "maxRetryWindow": 10800},
        }

        # `despatchMethod` should not be added for second class letters
        if postage == FIRST_CLASS:
            json_payload["standardParams"]["despatchMethod"] = "FIRST"
        elif postage == EUROPE:
            json_payload["standardParams"]["despatchMethod"] = "INTERNATIONAL_EU"
        elif postage == REST_OF_WORLD:
            json_payload["standardParams"]["despatchMethod"] = "INTERNATIONAL_ROW"
        elif postage == ECONOMY_CLASS:
            json_payload["standardParams"]["despatchMethod"] = "ECONOMY"

        return json_payload

    @staticmethod
    def _build_address(address_lines: list[str], last_line_key: Literal["postcode", "country"]):
        address_line_keys = ["line1", "line2", "line3", "line4", "line5"]

        last_line = address_lines[-1]

        # The first line has already been used as the recipient, so we include everything other than that.
        unstructured_address = dict(zip(address_line_keys, address_lines[:-1], strict=False))

        unstructured_address[last_line_key] = last_line

        return unstructured_address

    @staticmethod
    def _parse_bfpo_recipient_and_address(address: PostalAddress):
        address_line_keys = ["line1", "line2", "line3", "line4"]

        address_lines = address.bfpo_address_lines

        # We don't remove recipient here - DVLA API docs say that line1 should be:
        #    "Free text, expected to be SERVICE NUMBER, RANK and NAME."
        # Which is basically the recipient. Also if we don't include this, potentially we could not have a line 1
        # at all, which would break. As the address could simply be: recipient, BFPO 1234, BF1 1AA.
        recipient = address_lines[0]

        bfpo_address = dict(zip(address_line_keys, address_lines, strict=False))

        if address.postcode:
            bfpo_address["postcode"] = address.postcode

        bfpo_address["bfpoNumber"] = address.bfpo_number

        return recipient, bfpo_address

    def _parse_recipient_and_address(self, *, postage: str, address: PostalAddress):
        if address.is_bfpo_address:
            recipient, bfpo_address = self._parse_bfpo_recipient_and_address(address)
            return recipient, {"bfpoAddress": bfpo_address}

        address_lines = address.normalised_lines
        recipient = address_lines.pop(0)

        if postage in INTERNATIONAL_POSTAGE_TYPES:
            return recipient, {"internationalAddress": self._build_address(address_lines, "country")}

        return recipient, {"unstructuredAddress": self._build_address(address_lines, "postcode")}

    def _truncate_long_address_lines(self, address_data: dict) -> tuple[str, dict]:
        def truncate_line(key: str, value):
            if not isinstance(value, str):
                return value

            max_length = {"postcode": 10, "country": 256}.get(key, 45)
            return value[:max_length]

        # there'll only ever be one nested dict in address_data, but we dont know what the key is so we need to iterate
        for address_dict_type, address_dict in address_data.items():
            return {address_dict_type: {k: truncate_line(k, v) for k, v in address_dict.items()}}

        raise RuntimeError(f"Expected values in {address_data}")
