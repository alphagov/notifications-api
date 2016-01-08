from flask import Blueprint

user = Blueprint('user', __name__)

from app.user.views import rest
