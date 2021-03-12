from flask import Blueprint, jsonify, request

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

email_branding_blueprint = Blueprint('email_branding', __name__)
register_errors(email_branding_blueprint)


@email_branding_blueprint.route('', methods=['GET'])
def get_email_branding_options():
    email_branding_options = [o.serialize() for o in dao_get_email_branding_options()]
    return jsonify(email_branding=email_branding_options)


@email_branding_blueprint.route('/<uuid:email_branding_id>', methods=['GET'])
def get_email_branding_by_id(email_branding_id):
    email_branding = dao_get_email_branding_by_id(email_branding_id)
    return jsonify(email_branding=email_branding.serialize())


@email_branding_blueprint.route('', methods=['POST'])
def create_email_branding():
    data = request.get_json()

    validate(data, post_create_email_branding_schema)

    email_branding = EmailBranding(**data)
    if 'text' not in data.keys():
        email_branding.text = email_branding.name

    dao_create_email_branding(email_branding)
    return jsonify(data=email_branding.serialize()), 201


@email_branding_blueprint.route('/<uuid:email_branding_id>', methods=['POST'])
def update_email_branding(email_branding_id):
    data = request.get_json()

    validate(data, post_update_email_branding_schema)

    fetched_email_branding = dao_get_email_branding_by_id(email_branding_id)
    if 'text' not in data.keys() and 'name' in data.keys():
        data['text'] = data['name']
    dao_update_email_branding(fetched_email_branding, **data)

    return jsonify(data=fetched_email_branding.serialize()), 200
