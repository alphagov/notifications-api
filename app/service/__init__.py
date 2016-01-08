from flask import Blueprint

service = Blueprint('service', __name__)

from app.service.views import rest
