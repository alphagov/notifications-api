import secrets
import string
import time
from datetime import datetime, timedelta

import boto3
import jwt
import requests
from flask import current_app


class SSMParameter:
    # cache properties for up to a day. note that if another process/app changes the value,
    # this cache won't be automatically invalidated
    TTL = timedelta(days=1)

    def __init__(self, key, ssm_client):
        self.key = key
        self.ssm_client = ssm_client
        self.last_read_at = None
        self._value = None

    def get(self):
        if self._value is not None and self.last_read_at + self.TTL > datetime.utcnow():
            return self._value
        self.last_read_at = datetime.utcnow()
        self._value = self.ssm_client.get_parameter(Name=self.key, WithDecryption=True)["Parameter"]["Value"]
        return self._value

    def set(self, value):
        # this errors if the parameter doesn't exist yet in SSM as we haven't supplied a `Type`
        # this is fine for our purposes, as we'll always want to pre-seed this data.
        self.ssm_client.put_parameter(Name=self.key, Value=value, Overwrite=True)
        self._value = value
        self.last_read_at = datetime.utcnow()


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
        if not self._jwt_token or time.time() >= self._jwt_expires_at:
            self._jwt_token = self.authenticate()
            jwt_dict = jwt.decode(self._jwt_token, options={"verify_signature": False})
            self._jwt_expires_at = jwt_dict["exp"]

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

    def change_api_key(self):
        from app import redis_store

        with redis_store.get_lock(f"dvla-change-api-key-{self.dvla_username.get()}", timeout=60, blocking=False):
            response = self.request.post(
                f"{current_app.config['DVLA_API_BASE_URL']}/thirdparty-access/v1/new-api-key",
                headers={
                    "x-api-key": self.dvla_api_key.get(),
                    "Authorization": self.jwt_token,
                },
                json={
                    "userName": self.dvla_username.get(),
                    "password": self.dvla_password.get(),
                },
            )
            response.raise_for_status()

            self.dvla_api_key.set(response.json()["newApiKey"])

    def change_password(self):
        from app import redis_store

        new_password = self._generate_password()

        with redis_store.get_lock(f"dvla-change-password-{self.dvla_username.get()}", timeout=60, blocking=False):
            response = self.request.post(
                f"{current_app.config['DVLA_API_BASE_URL']}/thirdparty-access/v1/password",
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

    def send_letter(self):
        pass
