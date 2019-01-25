from celery import current_app
from sqlalchemy.exc import IntegrityError

from flask import Blueprint, jsonify, request

from app.dao.letter_branding_dao import (
    dao_get_all_letter_branding, dao_create_letter_branding,
    dao_update_letter_branding,
    dao_get_letter_branding_by_id
)
from app.errors import register_errors
from app.letter_branding.letter_branding_schema import post_letter_branding_schema
from app.models import LetterBranding
from app.schema_validation import validate

letter_branding_blueprint = Blueprint('letter_branding', __name__, url_prefix='/letter-branding')
register_errors(letter_branding_blueprint)


@letter_branding_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint
    """
    if 'domain' in str(exc):
        return jsonify(
            result='error',
            message={'name': ["Duplicate domain '{}'".format(
                exc.params.get('domain')
            )]}
        ), 400
    if 'name' in str(exc):
        return jsonify(
            result='error',
            message={'name': ["Duplicate name '{}'".format(
                exc.params.get('name')
            )]}
        ), 400
    if 'filename' in str(exc):
        return jsonify(
            result='error',
            message={'name': ["Duplicate filename '{}'".format(
                exc.params.get('fileaname')
            )]}
        ), 400
    current_app.logger.exception(exc)
    return jsonify(result='error', message="Internal server error"), 500


@letter_branding_blueprint.route('', methods=['GET'])
def get_all_letter_brands():
    letter_brands = dao_get_all_letter_branding()

    return jsonify([lb.serialize() for lb in letter_brands])


@letter_branding_blueprint.route('/<uuid:letter_branding_id>', methods=['GET'])
def get_letter_brand_by_id(letter_branding_id):
    letter_branding = dao_get_letter_branding_by_id(letter_branding_id)

    return jsonify(letter_branding.serialize()), 200


@letter_branding_blueprint.route('', methods=['POST'])
def create_letter_brand():
    data = request.get_json()

    validate(data, post_letter_branding_schema)

    letter_branding = LetterBranding(**data)
    dao_create_letter_branding(letter_branding)

    return jsonify(letter_branding.serialize()), 201


@letter_branding_blueprint.route('/<uuid:letter_branding_id>', methods=['POST'])
def update_letter_branding(letter_branding_id):
    data = request.get_json()

    validate(data, post_letter_branding_schema)

    letter_branding = dao_update_letter_branding(letter_branding_id, **data)

    return jsonify(letter_branding.serialize()), 201
