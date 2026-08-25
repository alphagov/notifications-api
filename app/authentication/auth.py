import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager, nullcontext
from functools import wraps

from cachetools.func import lfu_cache
from flask import current_app, g, request
from gds_metrics import Histogram
from notifications_python_client.authentication import (
    decode_jwt_token,
    get_token_issuer,
)
from notifications_python_client.errors import (
    TokenAlgorithmError,
    TokenDecodeError,
    TokenError,
    TokenExpiredError,
    TokenIssuerError,
)
from sqlalchemy.orm.exc import NoResultFound

from app import memo_resetters
from app.hashing import check_hash
from app.serialised_models import SerialisedService

GENERAL_TOKEN_ERROR_MESSAGE = "Invalid token: make sure your API token matches the example at https://docs.notifications.service.gov.uk/rest-api.html#authorisation-header"

AUTH_DB_CONNECTION_DURATION_SECONDS = Histogram(
    "auth_db_connection_duration_seconds",
    "Time taken to get DB connection and fetch service from database",
)


class AuthError(Exception):
    def __init__(self, message, code, service_id=None, api_key_id=None):
        self.message = {"token": [message]}
        self.short_message = message
        self.code = code
        self.service_id = service_id
        self.api_key_id = api_key_id

    def __str__(self):
        return (
            f"AuthError({self.short_message}, {self.code}, service_id={self.service_id}, api_key_id={self.api_key_id})"
        )

    def to_dict_v2(self):
        return {"status_code": self.code, "errors": [{"error": "AuthError", "message": self.short_message}]}


class InternalApiKey:
    def __init__(self, client_id, secret):
        self.secret = secret
        self.id = client_id
        self.expiry_date = None


def requires_no_auth():
    pass


def requires_admin_auth():
    requires_internal_auth(current_app.config.get("ADMIN_CLIENT_ID"))


def requires_functional_test_auth():
    requires_internal_auth(current_app.config.get("FUNCTIONAL_TESTS_CLIENT_ID"))


def requires_internal_auth(expected_client_id):
    if expected_client_id not in current_app.config.get("INTERNAL_CLIENT_API_KEYS"):
        raise TypeError("Unknown client_id for internal auth")

    auth_token = _get_auth_token(request)
    client_id = _get_token_issuer(auth_token)

    if client_id != expected_client_id:
        raise AuthError("Unauthorized: not allowed to perform this action", 401)

    api_keys = [
        InternalApiKey(client_id, secret) for secret in current_app.config.get("INTERNAL_CLIENT_API_KEYS")[client_id]
    ]

    _decode_jwt_token(auth_token, api_keys, client_id)
    g.service_id = client_id
    # If other headers are required (or this one is no longer needed) update the docs:
    # https://github.com/alphagov/notifications-manuals/wiki/Request-headers-used
    g.user_id = request.headers.get("X-Notify-User-Id")


def requires_auth():
    auth_token = _get_auth_token(request)
    issuer = _get_token_issuer(auth_token)  # ie the `iss` claim which should be a service ID

    try:
        service_id = uuid.UUID(issuer)
    except Exception as e:
        raise AuthError("Invalid token: service id is not the right data type", 403) from e

    try:
        with AUTH_DB_CONNECTION_DURATION_SECONDS.time():
            service = SerialisedService.from_id(service_id)
    except NoResultFound as e:
        raise AuthError("Invalid token: service not found", 403) from e

    if not service.api_keys:
        raise AuthError("Invalid token: service has no API keys", 403, service_id=service.id)

    if not service.active:
        raise AuthError("Invalid token: service is archived", 403, service_id=service.id)

    api_key = _decode_jwt_token(auth_token, service.api_keys, service.id)

    g.api_user = api_key
    g.service_id = service_id
    g.authenticated_service = service

    extra = {
        "service_id": service_id,
        "api_key_id": api_key.id,
        # If other headers are required (or this one no is longer needed) update the docs:
        # https://github.com/alphagov/notifications-manuals/wiki/Request-headers-used
        "issuer": request.headers.get("User-Agent"),
        "url": request.base_url,
    }
    current_app.logger.info(
        "API authorised for service %(service_id)s with api key %(api_key_id)s, "
        "using issuer %(issuer)s for URL: %(url)s",
        extra,
        extra=extra,
    )


def _decode_jwt_token(auth_token, api_keys, service_id=None):
    for api_key in api_keys:
        try:
            decode_jwt_token(auth_token, api_key.secret)
        except TokenExpiredError as e:
            err_msg = "Error: Your system clock must be accurate to within 30 seconds"
            extra = {
                "error_message": err_msg,
                "token_iat": e.token.get("iat"),
                "local_unix_time": int(time.time()),
                # If other headers are required (or this one no is longer needed) update the docs:
                # https://github.com/alphagov/notifications-manuals/wiki/Request-headers-used
                "cloudfront_request_id": request.headers.get("x-amz-cf-id"),
            }
            current_app.logger.info(
                "Rejecting user authentication with %(error_message)r "
                "(token.iat: %(token_iat)s, us: %(local_unix_time)s) [X-Amz-Cf-Id: %(cloudfront_request_id)s]",
                extra,
                extra=extra,
            )
            raise AuthError(err_msg, 403, service_id=service_id, api_key_id=api_key.id) from e
        except TokenAlgorithmError as e:
            err_msg = "Invalid token: algorithm used is not HS256"
            raise AuthError(err_msg, 403, service_id=service_id, api_key_id=api_key.id) from e
        except TokenDecodeError:
            # we attempted to validate the token but it failed meaning it was not signed using this api key.
            # Let's try the next one
            # TODO: Change this so it doesn't also catch `TokenIssuerError` or `TokenIssuedAtError` exceptions (which
            # are children of `TokenDecodeError`) as these should cause an auth error immediately rather than
            # continue on to check the next API key
            continue
        except TokenError as e:
            # General error when trying to decode and validate the token
            raise AuthError(GENERAL_TOKEN_ERROR_MESSAGE, 403, service_id=service_id, api_key_id=api_key.id) from e

        if api_key.expiry_date:
            raise AuthError("Invalid token: API key revoked", 403, service_id=service_id, api_key_id=api_key.id)

        return api_key
    else:
        # service has API keys, but none matching the one the user provided
        raise AuthError("Invalid token: API key not found", 403, service_id=service_id)


def _get_auth_token(req):
    auth_header = req.headers.get("Authorization", None)
    if not auth_header:
        raise AuthError("Unauthorized: authentication token must be provided", 401)

    auth_scheme = auth_header[:7].title()

    if auth_scheme != "Bearer ":
        raise AuthError("Unauthorized: authentication bearer scheme must be used", 401)

    return auth_header[7:]


def _get_token_issuer(auth_token):
    try:
        issuer = get_token_issuer(auth_token)
    except TokenIssuerError as e:
        raise AuthError("Invalid token: iss field not provided", 403) from e
    except TokenDecodeError as e:
        raise AuthError(GENERAL_TOKEN_ERROR_MESSAGE, 403) from e
    return issuer


# caching check_hash isn't ideal from a security POV as it does mean we'll be holding the plaintext
# password in-memory once it is used, but performing a bcrypt operation on every request may be quite
# punishing and/or open us up to some DoS attacks. using an LFU cache (rather than LRU) should at
# least stop a DoS attack being able to push our real requests' passwords out of the cache too easily.
_cached_check_hash = lfu_cache(maxsize=64, typed=True)(check_hash)


memo_resetters.append(lambda: _cached_check_hash.cache_clear())


@contextmanager
def _suppress_and_log_autherror() -> Generator:
    try:
        yield
    except AuthError as e:
        current_app.logger.warning("Suppressing basic auth failure: %s", str(e), extra={"exception": str(e)})


def requires_basic_auth(
    credentials_config_key: str,
    check_hash_callable: Callable[[str, str], bool] = _cached_check_hash,
    *,
    log_only: bool = False,
) -> None:
    """
    `credentials_config_key` is expected to be a key in the flask app config containing a mapping
    of usernames to bcrypt hashes of their basic auth passwords. a very low bcrypt difficulty can
    be used in the hashes if performance is a concern.

    For use as a `before_request` function, apply `credentials_config_key` with `functools.partial`.
    """
    auth = request.authorization
    creds_dict = current_app.config.get(credentials_config_key) or {}

    with _suppress_and_log_autherror() if log_only else nullcontext():
        if (not auth) or auth.type != "basic":
            current_app.logger.warning(
                "Request expecting basic auth from %s received no authorization header",
                credentials_config_key,
                extra={"credentials_config_key": credentials_config_key},
            )
            raise AuthError("Unauthorized: basic authorization must be provided", 401)

        if auth.username not in creds_dict:
            current_app.logger.warning(
                "Request's basic auth username %s not found in %s",
                auth.username,
                credentials_config_key,
                extra={"credentials_config_key": credentials_config_key, "username": auth.username},
            )
            raise AuthError("Unauthorized: basic authorisation failed", 403)

        if not check_hash_callable(auth.password or "", creds_dict[auth.username]):
            current_app.logger.warning(
                "Request's basic auth password for username %s does not match that found in %s",
                auth.username,
                credentials_config_key,
                extra={"credentials_config_key": credentials_config_key, "username": auth.username},
            )
            raise AuthError("Unauthorized: basic authorisation failed", 403)


def view_requires_basic_auth[**A, R](
    credentials_config_key: str,
    check_hash_callable: Callable[[str, str], bool] = _cached_check_hash,
    *,
    log_only: bool = False,
) -> Callable[[Callable[A, R]], Callable[A, R]]:
    """
    Returns a decorator function that will run `requires_basic_auth` before its wrapped function.

    For use applying `requires_basic_auth` to single views.
    """

    def basic_auth_decorator(inner: Callable[A, R]) -> Callable[A, R]:
        @wraps(inner)
        def view_wrapper(*args, **kwargs):
            requires_basic_auth(credentials_config_key, check_hash_callable, log_only=log_only)
            return inner(*args, **kwargs)

        return view_wrapper

    return basic_auth_decorator
