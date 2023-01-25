import boto3
import requests
from flask import current_app


class SSMParameter:
    def __init__(self, key, ssm_client):
        self.key = key
        self.ssm_client = ssm_client

    def get(self):
        return self.ssm_client.get_parameter(Name=self.key, WithDecryption=True)["Parameter"]["Value"]

    def set(self, value):
        # this errors if the parameter doesn't exist yet in SSM as we haven't supplied a `Type`
        # this is fine for our purposes, as we'll always want to pre-seed this data.
        self.ssm_client.put_parameter(Name=self.key, Value=value, Overwrite=True)


class DVLAClient:
    """
    DVLA HTTP API letter client.
    """

    statsd_client = None

    _jwt_token = None

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
        if not self._jwt_token:
            self._jwt_token = self.authenticate()

        return self._jwt_token

    def authenticate(self):
        """
        Fetch a JWT from the DVLA API that can be used in other DVLA API requests
        """
        response = self.request.post(
            f"{current_app.config['DVLA_API_BASE_URL']}/thirdparty-access/v1/authenticate",
            json={
                "userName": self.dvla_username.get(),
                "password": self.dvla_password.get(),
            },
        )
        response.raise_for_status()

        return response.json()["id-token"]

    def send_letter(self):
        pass
