from flask import Blueprint, request, abort
from jwt import decode, DecodeError
import calendar
import time
import base64
import hashlib
import hmac

AUTHORIZATION_HEADER = 'Authorization'
AUTHORIZATION_SCHEME = 'Bearer'
WINDOW = 1

main = Blueprint('main', __name__)


def get_secrets(service_identifier):
    """
    Temp method until secrets are stored in database etc
    :param service_identifier:
    :return: (Boolean, String)
    """
    secrets = {
        'service1': '1234'
    }
    if service_identifier not in secrets:
        return False, None
    return True, secrets[service_identifier]


def get_token_from_headers(headers):
    auth_header = headers.get(AUTHORIZATION_HEADER, '')
    if auth_header[:7] != AUTHORIZATION_SCHEME + " ":
        return None
    return auth_header[7:]


def token_is_valid(token):
    try:
        # decode token to get service identifier
        # signature not checked
        unverified = decode(token, verify=False, algorithms=['HS256'])

        # service identifier used to get secret
        found, secret = get_secrets(unverified['iss'])

        # use secret to validate the token
        verified = decode(token, key=secret.encode(), verify=True, algorithms=['HS256'])

        # check expiry
        if not calendar.timegm(time.gmtime()) < verified['iat'] + WINDOW:
            print("TIMESTAMP FAILED")
            return False

        # check request
        signed_url = base64.b64encode(
            hmac.new(
                secret.encode(),
                "{} {}".format(request.method, request.path).encode(),
                digestmod=hashlib.sha256
            ).digest()
        ).decode()
        if signed_url != verified['req']:
            print("URL FAILED")
            return False

        # check body
        signed_json_request = base64.b64encode(
            hmac.new(
                secret.encode(),
                request.data,
                digestmod=hashlib.sha256
            ).digest()
        ).decode()

        print(verified)

        if signed_json_request != verified['pay']:
            print("PAYLOAD FAILED")
            return False

    except DecodeError:
        print("TOKEN VERIFICATION FAILED")
        return False

    return True


def perform_authentication():
    incoming_token = get_token_from_headers(request.headers)
    if not incoming_token:
        abort(401)
    if not token_is_valid(incoming_token):
        abort(403)


main.before_request(perform_authentication)


from .views import notifications, index
from . import errors
