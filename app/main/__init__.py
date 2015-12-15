from flask import Blueprint
from app.main.authentication.auth import requires_auth

AUTHORIZATION_HEADER = 'Authorization'
AUTHORIZATION_SCHEME = 'Bearer'
WINDOW = 1

main = Blueprint('main', __name__)


main.before_request(requires_auth)


from .views import notifications, index
from . import errors
