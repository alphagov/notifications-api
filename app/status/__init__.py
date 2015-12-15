from flask import Blueprint

status = Blueprint('status', __name__)

from app.status.views import healthcheck
