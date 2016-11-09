import json

import pytest
from flask import url_for


@pytest.fixture(scope='function')
def app_for_test(mocker):
    import flask
    from flask import Blueprint
    from app.authentication.auth import AuthError
    from app.v2.errors import BadRequestError, TooManyRequestsError

    app = flask.Flask(__name__)
    app.config['TESTING'] = True

    from app.v2.errors import register_errors
    blue = Blueprint("v2_under_test", __name__, url_prefix='/v2/under_test')

    @blue.route("/raise_auth_error", methods=["GET"])
    def raising_auth_error():
        raise AuthError("some message", 403)

    @blue.route("/raise_bad_request", methods=["GET"])
    def raising_bad_request():
        raise BadRequestError(message="you forgot the thing")

    @blue.route("/raise_too_many_requests", methods=["GET"])
    def raising_too_many_requests():
        raise TooManyRequestsError(sending_limit="452")

    @blue.route("/raise_validation_error", methods=["GET"])
    def raising_validation_error():
        from app.schema_validation import validate
        from app.v2.notifications.notification_schemas import post_sms_request
        validate({"template_id": "bad_uuid"}, post_sms_request)

    register_errors(blue)
    app.register_blueprint(blue)

    return app


def test_auth_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_auth_error'))
            assert response.status_code == 403
            error = json.loads(response.get_data(as_text=True))
            assert error == {"status_code": 403,
                             "errors": [{"error": "AuthError",
                                         "message": "some message"}]}


def test_bad_request_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_bad_request'))
            assert response.status_code == 400
            error = json.loads(response.get_data(as_text=True))
            assert error == {"status_code": 400,
                             "errors": [{"error": "BadRequestError",
                                         "message": "you forgot the thing"}]}


def test_too_many_requests_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_too_many_requests'))
            assert response.status_code == 429
            error = json.loads(response.get_data(as_text=True))
            assert error == {"status_code": 429,
                             "errors": [{"error": "TooManyRequestsError",
                                         "message": "Exceeded send limits (452) for today"}]}


def test_validation_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for('v2_under_test.raising_validation_error'))
            assert response.status_code == 400
            error = json.loads(response.get_data(as_text=True))
            assert len(error.keys()) == 2
            assert error['status_code'] == 400
            assert len(error['errors']) == 2
            assert {'error': 'ValidationError',
                    'message': {'phone_number': 'is a required property'}} in error['errors']
            assert {'error': 'ValidationError',
                    'message': {'template_id': 'not a valid UUID'}} in error['errors']
