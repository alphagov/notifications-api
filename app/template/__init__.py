from flask import Blueprint

template = Blueprint('template', __name__)

from app.template import rest
