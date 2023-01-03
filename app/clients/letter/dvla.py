import random
import secrets
import string

import boto3
import redis_lock
import requests
from celery.exceptions import WorkerShutdown
from flask import current_app

# TODO: This file contains prototyping code. Many edge cases will not be covered. Consider scrapping this code and
#       starting from scratch when preparing for production use.
from app import redis_store


class DVLAClient:
    def __init__(self, username=None, password=None, api_key=None):
        self.username = username
        self.password = password
        self.api_key = api_key
        self.jwt_token = None
        self.aws_client = boto3.client("ssm")
        self.redis_client = redis_store.redis_store._redis_client

        # We could have separate locks for password and API key but it seems like overkill, especially for
        # proof-of-concept.
        self.lock = redis_lock.Lock(self.redis_client, "dvla-api-credentials", expire=60)

        # Proof-of-concept weirdness: we're now going to make some HTTP requests to:
        #   1) load credentials
        #   2) get a valid JWT so that we can start making authenticated API calls.
        # We'd probably want to re-think this as/when we productionise.
        self.load_credentials()
        self.authenticate()

    def _get_parameter_from_aws(self, name):
        return self.aws_client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]

    def _set_parameter_in_aws(self, name, value):
        self.aws_client.put_parameter(Name=name, Value=value, Overwrite=True)
        return True

    def _generate_password(self):
        """
        DVLA api password must be at least 8 characters in length and contain upper, lower, numerical and special
        characters.
        """
        new_password_as_list = list(secrets.token_urlsafe(32))
        character_categories = [string.ascii_uppercase, string.ascii_lowercase, string.digits, string.punctuation]

        for category in character_categories:
            new_password_as_list.append(category[random.randint(0, (len(category) - 1))])
        random.shuffle(new_password_as_list)
        return "".join(new_password_as_list)

    def _get_unauth_headers(self):
        return {
            "Accept": "application/json",
        }

    def _get_auth_headers(self):
        headers = self._get_unauth_headers()
        headers |= {
            "Authorization": self.jwt_token,
            "X-API-Key": self.api_key,
        }
        return headers

    def _unauthenticated_request(self, method: str, url: str, json=None):
        response = requests.request(method, url, headers=self._get_unauth_headers(), json=json)

        current_app.logger.warning("unauthenticated request: {data}", extra=dict(data=response))
        current_app.logger.warning("unauthenticated request: {data}", extra=dict(data=response.text))

        return response

    def _authenticated_request(self, method: str, url: str, json=None):
        def _do_request(step):
            _response = requests.request(method, url, headers=self._get_auth_headers(), json=json)
            current_app.logger.warning("{step} {data}", extra=dict(step=step, data=_response))
            current_app.logger.warning("{step} {data}", extra=dict(step=step, data=_response.text))
            return _response

        response = _do_request("authenticated request attempt 1:")

        return response

    def _request(self, method: str, url: str, authenticated: bool, json=None):
        if not authenticated:
            response = self._unauthenticated_request(method, url, json=json)

        else:
            response = self._authenticated_request(method, url, json=json)

        response.raise_for_status()

        return response.json()

    def _get(self, url: str, authenticated: bool):
        return self._request("get", url, authenticated=authenticated)

    def _post(self, url, authenticated: bool, json=None):
        return self._request("post", url, authenticated=authenticated, json=json)

    def load_credentials(self):
        """Load API credentials from AWS SSM Parameter Store."""
        self.username = self._get_parameter_from_aws(current_app.config["SSM_INTEGRATION_DVLA_USERNAME"])
        self.password = self._get_parameter_from_aws(current_app.config["SSM_INTEGRATION_DVLA_PASSWORD"])
        self.api_key = self._get_parameter_from_aws(current_app.config["SSM_INTEGRATION_DVLA_API_KEY"])

    def authenticate(self):
        """Fetch a JWT from the DVLA API that can be used in other DVLA API requests"""
        authenticate_api_base_url = current_app.config["DVLA_AUTHENTICATE_API_BASE_URL"]

        response = self._post(
            f"{authenticate_api_base_url}/v1/authenticate",
            authenticated=False,
            json={
                "userName": self.username,
                "password": self.password,
            },
        )
        self.jwt_token = response["id-token"]

        current_app.logger.info("Authenticated successfully to DVLA API")
        return self.jwt_token

    def rotate_password(self):
        # TODO: We should think about whether it's possible for us to "lose" this password, eg DVLA updates it
        #       but we fail to store the updated password in SSM.
        if not self.lock.acquire(blocking=False):
            raise WorkerShutdown(
                "Could not acquire lock to rotate DVLA API Password. "
                "Either deadlocked or another process is in this codeblock. "
                "If deadlocked, lock _should_ auto-release after 60 seconds. "
                "Killing worker."
            )

        try:
            new_password = self._generate_password()
            current_app.logger.warning(f"Updating DVLA API password to: {new_password}")

            authenticate_api_base_url = current_app.config["DVLA_AUTHENTICATE_API_BASE_URL"]
            self._post(
                f"{authenticate_api_base_url}/v1/password",
                authenticated=False,
                json={
                    "userName": self.username,
                    "password": self.password,
                    "newPassword": new_password,
                },
            )

            # We store the new password on the client so that it can immediately get new valid JWT tokens without
            # having to go to Parameter Store.
            self.password = new_password
            self._set_parameter_in_aws(current_app.config["SSM_INTEGRATION_DVLA_PASSWORD"], new_password)

            return self.password

        finally:
            self.lock.release()

    def rotate_api_key(self):
        # TODO: We should think about whether it's possible for us to "lose" this api key, eg DVLA updates it
        #       but we fail to store the updated key in SSM.
        if not self.lock.acquire(blocking=False):
            raise WorkerShutdown(
                "Could not acquire lock to rotate DVLA API Key. "
                "Either deadlocked or another process is in this codeblock. "
                "If deadlocked, lock _should_ auto-release after 60 seconds. "
                "Killing worker."
            )

        try:
            authenticate_api_base_url = current_app.config["DVLA_AUTHENTICATE_API_BASE_URL"]
            response = self._post(
                f"{authenticate_api_base_url}/v1/new-api-key",
                authenticated=True,
            )

            new_api_key = response["newApiKey"]
            self._set_parameter_in_aws(current_app.config["SSM_INTEGRATION_DVLA_API_KEY"], new_api_key)

            # We specifically do *not* store the new API key on the client here, as changing the API key is not a
            # perfectly consistent operation. It takes a few seconds for various DVLA APIs to recognise the update.
            # So it's possible for the current API key/JWT to continue working for a few seconds.

            return new_api_key

        finally:
            self.lock.release()

    def get_print_job(self, job_id):
        """
        This method stub is for us to be able to check that once jwt token expires and we can automatically
        create a new one.
        """
        print_api_base_url = current_app.config["DVLA_PRINT_API_BASE_URL"]
        response = self._get(
            f"{print_api_base_url}/v1/print/jobs/{job_id}",
            authenticated=True,
        )
        return response
