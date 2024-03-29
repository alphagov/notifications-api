from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.dao.email_branding_dao import (
    dao_archive_email_branding,
    dao_create_email_branding,
    dao_get_email_branding_by_id,
    dao_get_email_branding_by_name_case_insensitive,
    dao_get_email_branding_options,
    dao_get_existing_alternate_email_branding_for_name,
    dao_get_orgs_and_services_associated_with_email_branding,
    dao_update_email_branding,
)
from app.dao.organisation_dao import (
    dao_get_all_organisations_with_specific_email_branding_in_their_pool,
    dao_remove_email_branding_from_organisation_pool,
)
from app.email_branding.email_branding_schema import (
    post_create_email_branding_schema,
    post_get_email_branding_name_for_alt_text_schema,
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


@email_branding_blueprint.route("/get-name-for-alt-text/", methods=["POST"])
def get_email_branding_name_for_alt_text():
    data = request.get_json()

    validate(data, post_get_email_branding_name_for_alt_text_schema)

    alt_text = data["alt_text"]

    existing_branding = dao_get_email_branding_by_name_case_insensitive(alt_text)
    if not existing_branding:
        chosen_name = alt_text
    else:
        existing_alternate_branding_options = {
            x.name for x in dao_get_existing_alternate_email_branding_for_name(alt_text)
        }

        for i in range(1, 100):
            potential_name = f"{alt_text} (alternate {i})"
            if potential_name not in existing_alternate_branding_options:
                chosen_name = potential_name
                break
        else:
            raise ValueError(f"Couldnt assign a unique name for {alt_text} - already too many options")

    return jsonify(name=chosen_name), 200


@email_branding_blueprint.route("/<uuid:email_branding_id>/orgs_and_services", methods=["GET"])
def get_orgs_and_services_associated_with_email_branding(email_branding_id):
    orgs_and_services = dao_get_orgs_and_services_associated_with_email_branding(email_branding_id)

    return jsonify(data=orgs_and_services), 200


@email_branding_blueprint.route("/<uuid:email_branding_id>/archive", methods=["POST"])
def archive_email_branding(email_branding_id):
    orgs_and_services = dao_get_orgs_and_services_associated_with_email_branding(email_branding_id)

    # check branding not used
    if len(orgs_and_services["services"]) > 0 or len(orgs_and_services["organisations"]) > 0:
        return (
            jsonify(result="error", message="Email branding is in use and so it can't be archived."),
            400,
        )

    # delete branding from branding pools if it's in any
    orgs_with_pools_to_clean = dao_get_all_organisations_with_specific_email_branding_in_their_pool(email_branding_id)
    for org in orgs_with_pools_to_clean:
        dao_remove_email_branding_from_organisation_pool(org.id, email_branding_id)

    # archive branding and rename it, NOTE: make sure it doesn't show up anywhere when archived
    # - neither on list of brandings in platform admin view, nor in brandings that can be added to pools
    dao_archive_email_branding(email_branding_id)

    return "", 204
