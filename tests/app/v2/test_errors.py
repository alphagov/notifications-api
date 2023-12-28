import pytest
from flask import url_for
from flask_openapi3 import OpenAPI
from notifications_utils.recipients import InvalidPhoneError
from sqlalchemy.exc import DataError


@pytest.fixture(scope="function")
def app_for_test():
    from flask import Blueprint

    from app import init_app
    from app.authentication.auth import AuthError
    from app.v2.errors import BadRequestError, TooManyRequestsError

    app = OpenAPI(__name__)
    app.config["TESTING"] = True
    init_app(app)
    from app import statsd_client

    statsd_client.init_app(app)

    from app.v2.errors import register_errors

    blue = Blueprint("v2_under_test", __name__, url_prefix="/v2/under_test")

    @blue.route("/raise_auth_error", methods=["GET"])
    def raising_auth_error():
        raise AuthError("some message", 403)

    @blue.route("/raise_bad_request", methods=["GET"])
    def raising_bad_request():
        raise BadRequestError(message="you forgot the thing")

    @blue.route("/raise_too_many_requests", methods=["GET"])
    def raising_too_many_requests():
        raise TooManyRequestsError(limit_name="total", sending_limit="452")

    @blue.route("/raise_validation_error", methods=["GET"])
    def raising_validation_error():
        from app.schema_validation import validate
        from app.v2.notifications.notification_schemas import post_sms_request

        validate({"template_id": "bad_uuid"}, post_sms_request)

    @blue.route("raise_data_error", methods=["GET"])
    def raising_data_error():
        raise DataError("There was a db problem", "params", "orig")

    @blue.route("raise_phone_error/<error_id>", methods=["GET"])
    def raising_invalid_phone_error(error_id):
        errors = {
            "symbol": "Mobile numbers can only include: 0 1 2 3 4 5 6 7 8 9 ( ) + -",
            "too-short": "Mobile number is too long",
            "too-long": "Mobile number is too short",
            "invalid-country": "Country code not found - double check the mobile number you entered",
            "invalid-uk": "This does not look like a UK mobile number - double check the mobile number you entered",
        }
        raise InvalidPhoneError(errors[error_id])

    @blue.route("raise_exception", methods=["GET"])
    def raising_exception():
        raise AssertionError("Raising any old exception")

    register_errors(blue)
    app.register_blueprint(blue)

    return app


def test_auth_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for("v2_under_test.raising_auth_error"))
            assert response.status_code == 403
            error = response.json
            assert error == {"status_code": 403, "errors": [{"error": "AuthError", "message": "some message"}]}


def test_bad_request_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for("v2_under_test.raising_bad_request"))
            assert response.status_code == 400
            error = response.json
            assert error == {
                "status_code": 400,
                "errors": [{"error": "BadRequestError", "message": "you forgot the thing"}],
            }


def test_too_many_requests_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for("v2_under_test.raising_too_many_requests"))
            assert response.status_code == 429
            error = response.json
            assert error == {
                "status_code": 429,
                "errors": [{"error": "TooManyRequestsError", "message": "Exceeded send limits (total: 452) for today"}],
            }


def test_validation_error(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for("v2_under_test.raising_validation_error"))
            assert response.status_code == 400
            error = response.json
            assert len(error.keys()) == 2
            assert error["status_code"] == 400
            assert len(error["errors"]) == 2
            assert {"error": "ValidationError", "message": "phone_number is a required property"} in error["errors"]
            assert {"error": "ValidationError", "message": "template_id is not a valid UUID"} in error["errors"]


def test_data_errors(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for("v2_under_test.raising_data_error"))
            assert response.status_code == 404
            error = response.json
            assert error == {"status_code": 404, "errors": [{"error": "DataError", "message": "No result found"}]}


def test_internal_server_error_handler(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for("v2_under_test.raising_exception"))
            assert response.status_code == 500
            error = response.json
            assert error == {
                "status_code": 500,
                "errors": [{"error": "AssertionError", "message": "Internal server error"}],
            }


def test_bad_method(app_for_test):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.post(url_for("v2_under_test.raising_exception"))

            assert response.status_code == 405

            assert response.get_json(force=True) == {
                "result": "error",
                "message": "The method is not allowed for the requested URL.",
            }


@pytest.mark.parametrize(
    "error_id, expected_response",
    (
        ("symbol", "Must not contain letters or symbols"),
        ("too-short", "Too many digits"),
        ("too-long", "Not enough digits"),
        ("invalid-country", "Not a valid country prefix"),
        ("invalid-uk", "Not a UK mobile number"),
    ),
)
def test_invalid_phone_error(app_for_test, error_id, expected_response):
    with app_for_test.test_request_context():
        with app_for_test.test_client() as client:
            response = client.get(url_for("v2_under_test.raising_invalid_phone_error", error_id=error_id))
            assert response.status_code == 400
            assert response.json == {
                "status_code": 400,
                "errors": [{"error": "InvalidPhoneError", "message": expected_response}],
            }
