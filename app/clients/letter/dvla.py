import base64
import secrets
import string
import time

import boto3
import jwt
import requests
from flask import current_app

from app.clients import ClientException


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


class DVLAClient:
    """
    DVLA HTTP API letter client.
    """

    statsd_client = None

    _jwt_token = None
    _jwt_expires_at = None

    def init_app(self, region, statsd_client):
        ssm_client = boto3.client("ssm", region_name=region)
        self.dvla_username = SSMParameter(key="/notify/api/dvla_username", ssm_client=ssm_client)
        self.dvla_password = SSMParameter(key="/notify/api/dvla_password", ssm_client=ssm_client)
        self.dvla_api_key = SSMParameter(key="/notify/api/dvla_api_key", ssm_client=ssm_client)

        self.statsd_client = statsd_client
        self.request = requests.Session()

    @property
    def name(self):
        return "dvla"

    @property
    def jwt_token(self):
        # if the jwt is about to expire, just reset it ourselves to avoid unnecessary 401s
        buffer = 60
        if not self._jwt_token or time.time() + buffer >= self._jwt_expires_at:
            self._jwt_token = self.authenticate()
            jwt_dict = jwt.decode(self._jwt_token, options={"verify_signature": False})
            self._jwt_expires_at = jwt_dict["exp"]

        return self._jwt_token

    def _handle_common_dvla_errors(self, e: requests.HTTPError):
        if e.response.status_code == 429:
            raise DvlaThrottlingException() from e
        elif e.response.status_code >= 500:
            raise DvlaRetryableException() from e
        else:
            raise DvlaNonRetryableException() from e

    def authenticate(self):
        """
        Fetch a JWT from the DVLA API that can be used in other DVLA API requests
        """
        try:
            response = self.request.post(
                f"{current_app.config['DVLA_API_BASE_URL']}/thirdparty-access/v1/authenticate",
                json={
                    "userName": self.dvla_username.get(),
                    "password": self.dvla_password.get(),
                },
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                # likely the old password has already expired
                current_app.logger.exception("Failed to generate a DVLA jwt token")

                self.dvla_password.clear()
                raise DvlaRetryableException(e.response.json()[0]["detail"]) from e

            self._handle_common_dvla_errors(e)

        return response.json()["id-token"]

    def change_api_key(self):
        from app import redis_store

        with redis_store.get_lock(f"dvla-change-api-key-{self.dvla_username.get()}", timeout=60, blocking=False):
            # clear and re-fetch dvla api key, just to ensure we have the latest version
            self.dvla_api_key.clear()

            try:
                response = self.request.post(
                    f"{current_app.config['DVLA_API_BASE_URL']}/thirdparty-access/v1/new-api-key",
                    headers=self._get_auth_headers(),
                )
                response.raise_for_status()
            except requests.HTTPError as e:
                if e.response.status_code == 401:
                    # the api key is invalid, but we know it's current as per SSM as we fetched it at the beginning of
                    # this block. It feels most likely that the api key has just been changed by another process and
                    # DVLA's eventual consistency hasn't caught up yet. The other alternative is that the key expired
                    # due to being a year old - at which point we need to manually reset it
                    current_app.logger.exception("Failed to change DVLA api key")

                    self.dvla_api_key.clear()
                    raise DvlaNonRetryableException(e.response.json()[0]["detail"]) from e

                self._handle_common_dvla_errors(e)

            self.dvla_api_key.set(response.json()["newApiKey"])

    def change_password(self):
        from app import redis_store

        new_password = self._generate_password()

        with redis_store.get_lock(f"dvla-change-password-{self.dvla_username.get()}", timeout=60, blocking=False):
            # clear and re-fetch dvla password, just to ensure we have the latest version
            self.dvla_password.clear()

            try:
                response = self.request.post(
                    f"{current_app.config['DVLA_API_BASE_URL']}/thirdparty-access/v1/password",
                    json={
                        "userName": self.dvla_username.get(),
                        "password": self.dvla_password.get(),
                        "newPassword": new_password,
                    },
                )
                response.raise_for_status()
            except requests.HTTPError as e:
                if e.response.status_code == 401:
                    # the password is invalid, but we know it's current as per SSM as we fetched it at the beginning of
                    # this block. It feels most likely that the password has just been changed by another process and
                    # DVLA's eventual consistency hasn't caught up yet. The other alternative is that the key expired
                    # due to being 90 days old - at which point we need to manually reset it
                    current_app.logger.exception("Failed to change DVLA password")

                    self.dvla_password.clear()
                    raise DvlaNonRetryableException(e.response.json()[0]["detail"]) from e

                self._handle_common_dvla_errors(e)

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
        address: list[str],
        postage: str,
        service_id: str,
        organisation_id: str,
        pdf_file: bytes,
    ):
        """
        Sends a letter to the DVLA for printing

        address should be normalised address lines, e.g. ['A. User', 'London', 'SW1 1AA']
        """
        current_app.logger.info(f"Sending letter with id {notification_id}")

        try:
            response = self.request.post(
                f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
                headers=self._get_auth_headers(),
                json=self._format_create_print_job_json(
                    notification_id=notification_id,
                    reference=reference,
                    address_lines=address,
                    postage=postage,
                    service_id=service_id,
                    organisation_id=organisation_id,
                    pdf_file=pdf_file,
                ),
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            # Catch errors and raise our own to indicate what action to take.
            # If the error has details, we add them to the error message.
            if e.response.status_code == 400:
                raise DvlaNonRetryableException(e.response.json()["errors"][0]["detail"]) from e
            elif e.response.status_code in {401, 403}:
                # probably the api key is not valid
                self.dvla_api_key.clear()

                raise DvlaUnauthorisedRequestException(e.response.json()["errors"][0]["detail"]) from e
            elif e.response.status_code == 409:
                raise DvlaDuplicatePrintRequestException(e.response.json()["errors"][0]["detail"]) from e

            self._handle_common_dvla_errors(e)
        else:
            return response.json()

    def _format_create_print_job_json(
        self, *, notification_id, reference, address_lines, postage, service_id, organisation_id, pdf_file
    ):
        from app.constants import EUROPE, FIRST_CLASS, REST_OF_WORLD

        recipient_name = address_lines[0]
        address_without_recipient = address_lines[1:]

        json_payload = {
            "id": notification_id,
            "standardParams": {
                "jobType": "NOTIFY",
                "templateReference": "NOTIFY",
                "businessIdentifier": reference,
                "recipientName": recipient_name,
                "address": self._build_address_object(
                    postage=postage, address_without_recipient=address_without_recipient
                ),
            },
            "customParams": [
                {"key": "pdfContent", "value": base64.b64encode(pdf_file).decode("utf-8")},
                {"key": "organisationIdentifier", "value": organisation_id},
                {"key": "serviceIdentifier", "value": service_id},
            ],
        }

        # `despatchMethod` should not be added for second class letters
        if postage == FIRST_CLASS:
            json_payload["standardParams"]["despatchMethod"] = "FIRST"
        elif postage == EUROPE:
            json_payload["standardParams"]["despatchMethod"] = "INTERNATIONAL_EU"
        elif postage == REST_OF_WORLD:
            json_payload["standardParams"]["despatchMethod"] = "INTERNATIONAL_ROW"

        return json_payload

    @staticmethod
    def _build_unstructured_address(address_without_recipient):
        address_line_keys = ["line1", "line2", "line3", "line4", "line5"]

        postcode = address_without_recipient[-1]
        address_without_postcode = address_without_recipient[:-1]

        unstructured_address = dict(zip(address_line_keys, address_without_postcode))
        unstructured_address["postcode"] = postcode

        return unstructured_address

    @staticmethod
    def _build_international_address(address_without_recipient):
        address_line_keys = ["line1", "line2", "line3", "line4", "line5"]

        country = address_without_recipient[-1]
        address_without_country = address_without_recipient[:-1]

        international_address = dict(zip(address_line_keys, address_without_country))
        international_address["country"] = country

        return international_address

    def _build_address_object(self, *, postage, address_without_recipient):
        from app.constants import INTERNATIONAL_POSTAGE_TYPES

        if postage in INTERNATIONAL_POSTAGE_TYPES:
            return {"internationalAddress": self._build_international_address(address_without_recipient)}

        return {"unstructuredAddress": self._build_unstructured_address(address_without_recipient)}
