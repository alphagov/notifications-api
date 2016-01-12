from flask import Blueprint

main = Blueprint('main', __name__)

from app.main.views import index
