from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.dao.email_branding_dao import (
    dao_create_email_branding,
    dao_get_email_branding_by_id,
    dao_get_email_branding_options,
    dao_update_email_branding,
)
from app.email_branding.email_branding_schema import (
    post_create_email_branding_schema,
    post_update_email_branding_schema,
)
from app.errors import register_errors
from app.models import EmailBranding
from app.schema_validation import validate

email_branding_blueprint = Blueprint("email_branding", __name__)
register_errors(email_branding_blueprint)


@email_branding_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint
    """
    if exc.orig.diag.constraint_name == EmailBranding.CONSTRAINT_UNIQUE_NAME:
        return jsonify(result="error", message={"name": ["An email branding with that name already exists."]}), 400

    if exc.orig.diag.constraint_name == EmailBranding.CONSTRAINT_CHECK_ONE_OF_ALT_TEXT_TEXT_NULL:
        return (
            jsonify(result="error", message="Email branding must have exactly one of alt_text and text."),
            400,
        )

    current_app.logger.exception(exc)
    return jsonify(result="error", message="Internal server error"), 500


@email_branding_blueprint.route("", methods=["GET"])
def get_email_branding_options():
    email_branding_options = [o.serialize() for o in dao_get_email_branding_options()]
    return jsonify(email_branding=email_branding_options)


@email_branding_blueprint.route("/<uuid:email_branding_id>", methods=["GET"])
def get_email_branding_by_id(email_branding_id):
    email_branding = dao_get_email_branding_by_id(email_branding_id)
    return jsonify(email_branding=email_branding.serialize())


@email_branding_blueprint.route("", methods=["POST"])
def create_email_branding():
    data = request.get_json()

    validate(data, post_create_email_branding_schema)

    email_branding = EmailBranding(**data)

    dao_create_email_branding(email_branding)

    return jsonify(data=email_branding.serialize()), 201


@email_branding_blueprint.route("/<uuid:email_branding_id>", methods=["POST"])
def update_email_branding(email_branding_id):
    data = request.get_json()

    validate(data, post_update_email_branding_schema)

    fetched_email_branding = dao_get_email_branding_by_id(email_branding_id)

    dao_update_email_branding(fetched_email_branding, **data)

    return jsonify(data=fetched_email_branding.serialize()), 200
