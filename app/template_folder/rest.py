from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.dao.template_folder_dao import (
    dao_create_template_folder,
    dao_get_template_folder_by_id,
    dao_update_template_folder,
    dao_delete_template_folder
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.errors import register_errors
from app.models import TemplateFolder
from app.template_folder.template_folder_schema import (
    post_create_template_folder_schema,
    post_rename_template_folder_schema
)
from app.schema_validation import validate

template_folder_blueprint = Blueprint(
    'template_folder',
    __name__,
    url_prefix='/service/<uuid:service_id>/template-folder'
)
register_errors(template_folder_blueprint)


@template_folder_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    if 'template_folder_parent_id_fkey' in str(exc):
        return jsonify(result='error', message='parent_id not found'), 400

    raise


@template_folder_blueprint.route('', methods=['GET'])
def get_template_folders_for_service(service_id):
    service = dao_fetch_service_by_id(service_id)

    template_folders = [o.serialize() for o in service.all_template_folders]
    return jsonify(template_folders=template_folders)


@template_folder_blueprint.route('', methods=['POST'])
def create_template_folder(service_id):
    data = request.get_json()

    validate(data, post_create_template_folder_schema)

    template_folder = TemplateFolder(
        service_id=service_id,
        name=data['name'].strip(),
        parent_id=data['parent_id']
    )

    dao_create_template_folder(template_folder)

    return jsonify(data=template_folder.serialize()), 201


@template_folder_blueprint.route('/<uuid:template_folder_id>/rename', methods=['POST'])
def rename_template_folder(service_id, template_folder_id):
    data = request.get_json()

    validate(data, post_rename_template_folder_schema)

    template_folder = dao_get_template_folder_by_id(template_folder_id)
    template_folder.name = data['name']

    dao_update_template_folder(template_folder)

    return jsonify(data=template_folder.serialize()), 200


@template_folder_blueprint.route('/<uuid:template_folder_id>', methods=['DELETE'])
def delete_template_folder(service_id, template_folder_id):
    template_folder = dao_get_template_folder_by_id(template_folder_id)

    # don't allow deleting if there's anything in the folder (even if it's just more empty subfolders)
    if template_folder.subfolders or template_folder.templates:
        return jsonify(result='error', message='Folder is not empty'), 400

    dao_delete_template_folder(template_folder)

    return '', 204
