import boto3
import requests
from flask import current_app

# TODO: This file contains prototyping code. Many edge cases will not be covered. Consider scrapping this code and
#       starting from scratch when preparing for production use.


class DVLAClient:
    def __init__(self, username=None, password=None, api_key=None):
        self.username = username
        self.password = password
        self.api_key = api_key
        self.jwt_token = None
        self.aws_client = boto3.client("ssm")

        # Proof-of-concept weirdness: we're now going to make some HTTP requests to:
        #   1) load credentials
        #   2) get a valid JWT so that we can start making authenticated API calls.
        # We'd probably want to re-think this as/when we productionise.
        self.load_credentials()
        self.authenticate()

    def _get_parameter_from_aws(self, name):
        return self.aws_client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]

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
