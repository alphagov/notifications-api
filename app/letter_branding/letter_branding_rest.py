from celery import current_app
from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.dao.letter_branding_dao import (
    dao_create_letter_branding,
    dao_get_all_letter_branding,
    dao_get_existing_alternate_letter_branding_for_name,
    dao_get_letter_branding_by_id,
    dao_get_letter_branding_by_name_case_insensitive,
    dao_get_orgs_and_services_associated_with_letter_branding,
    dao_update_letter_branding,
)
from app.errors import register_errors
from app.letter_branding.letter_branding_schema import (
    post_create_letter_branding_schema,
    post_get_unique_name_for_letter_branding_schema,
    post_update_letter_branding_schema,
)
from app.models import LetterBranding
from app.schema_validation import validate

letter_branding_blueprint = Blueprint("letter_branding", __name__, url_prefix="/letter-branding")
register_errors(letter_branding_blueprint)


@letter_branding_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint
    """
    for col in {"name", "filename"}:
        if f"letter_branding_{col}_key" in str(exc):
            return jsonify(result="error", message={col: [f"{col.title()} already in use"]}), 400
    current_app.logger.exception(exc)
    return jsonify(result="error", message="Internal server error"), 500


@letter_branding_blueprint.route("", methods=["GET"])
def get_all_letter_brands():
    letter_brands = dao_get_all_letter_branding()

    return jsonify([lb.serialize() for lb in letter_brands])


@letter_branding_blueprint.route("/<uuid:letter_branding_id>", methods=["GET"])
def get_letter_brand_by_id(letter_branding_id):
    letter_branding = dao_get_letter_branding_by_id(letter_branding_id)

    return jsonify(letter_branding.serialize()), 200


@letter_branding_blueprint.route("", methods=["POST"])
def create_letter_brand():
    data = request.get_json()

    validate(data, post_create_letter_branding_schema)

    letter_branding = LetterBranding(**data)
    dao_create_letter_branding(letter_branding)

    return jsonify(letter_branding.serialize()), 201


@letter_branding_blueprint.route("/<uuid:letter_branding_id>", methods=["POST"])
def update_letter_branding(letter_branding_id):
    data = request.get_json()

    validate(data, post_update_letter_branding_schema)

    letter_branding = dao_update_letter_branding(letter_branding_id, **data)

    return jsonify(letter_branding.serialize()), 201


@letter_branding_blueprint.route("/<uuid:letter_branding_id>/orgs_and_services", methods=["GET"])
def get_orgs_and_services_associated_with_letter_branding(letter_branding_id):
    orgs_and_services = dao_get_orgs_and_services_associated_with_letter_branding(letter_branding_id)

    return jsonify(data=orgs_and_services), 200


@letter_branding_blueprint.route("/get-unique-name/", methods=["POST"])
def get_letter_branding_unique_name():
    data = request.get_json()

    validate(data, post_get_unique_name_for_letter_branding_schema)

    name = data["name"]

    existing_branding = dao_get_letter_branding_by_name_case_insensitive(name)
    if not existing_branding:
        chosen_name = name
    else:
        existing_alternate_branding_options = {
            x.name for x in dao_get_existing_alternate_letter_branding_for_name(name)
        }

        for i in range(1, 100):
            potential_name = f"{name} (alternate {i})"
            if potential_name not in existing_alternate_branding_options:
                chosen_name = potential_name
                break
        else:
            raise ValueError(f"Couldnt assign a unique name for {name} - already too many options")

    return jsonify(name=chosen_name), 200
