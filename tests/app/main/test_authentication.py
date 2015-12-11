from flask import json
import jwt
import hashlib
import hmac
import calendar
import time
import base64


def sign_a_thing(thing_to_sign, secret_key):
    return base64.b64encode(
        hmac.new(
            secret_key.encode(),
            thing_to_sign.encode(),
            digestmod=hashlib.sha256
        ).digest()
    )


def token(request_method, request_url, secret_key, service_id, json_body):

    # request method and resource path - hash of request url - POST /path-to-resource
    signed_url = sign_a_thing("{} {}".format(request_method, request_url), secret_key)
    signed_payload = sign_a_thing(json_body, secret_key)

    headers = {
        "typ": "JWT",
        "alg": "HS256"
    }

    claims = {
        'iss': service_id,  # issued by - identified by id of the service
        'iat': calendar.timegm(time.gmtime()),  # issued at in epoch seconds
        'req': signed_url.decode(),
        'pay': signed_payload.decode()  # signed payload
    }

    return jwt.encode(payload=claims, key=secret_key, headers=headers).decode()


def test_should_not_allow_request_with_no_token(notify_api):
    response = notify_api.test_client().get("/")
    assert response.status_code == 401
    data = json.loads(response.get_data())
    assert data['error'] == 'Unauthorized, authentication token must be provided'


def test_should_not_allow_request_with_invalid_token(notify_api):
    response = notify_api.test_client().get(
        "/",
        headers={'Authorization': 'Bearer 1234'}
    )
    assert response.status_code == 403
    data = json.loads(response.get_data())
    assert data['error'] == 'Forbidden, invalid authentication token provided'


def test_should_allow_request_with_valid_token(notify_api):

    body = {
        "1": "A",
        "3": "A",
        "7": "A",
        "15": "A",
        "2": "B"
    }
    request_body = json.dumps(body)

    request_token = token("POST", "/", "1234", "service1", request_body)

    # from time import sleep
    # sleep(4)

    response = notify_api.test_client().post(
        "/",
        data=request_body,
        headers={
            'Authorization': "Bearer {}".format(request_token)
        },
        content_type='application/json'
    )
    assert response.status_code == 200
