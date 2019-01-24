from flask import Blueprint

from app.errors import register_errors

email_branding_blueprint = Blueprint('letter_branding', __name__, url_prefix='letter-branding')
register_errors(email_branding_blueprint)