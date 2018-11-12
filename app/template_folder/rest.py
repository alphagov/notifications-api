from flask import Blueprint, jsonify, request, current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app.dao.dao_utils import transactional
from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.dao.template_folder_dao import (
    dao_create_template_folder,
    dao_get_template_folder_by_id_and_service_id,
    dao_update_template_folder,
    dao_delete_template_folder
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.errors import InvalidRequest, register_errors
from app.models import TemplateFolder
from app.template_folder.template_folder_schema import (
    post_create_template_folder_schema,
    post_rename_template_folder_schema,
    post_move_template_folder_schema,
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

    if data.get('parent_id') is not None:
        try:
            dao_get_template_folder_by_id_and_service_id(data['parent_id'], service_id)
        except NoResultFound:
            raise InvalidRequest("parent_id not found", status_code=400)

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

    template_folder = dao_get_template_folder_by_id_and_service_id(template_folder_id, service_id)
    template_folder.name = data['name']

    dao_update_template_folder(template_folder)

    return jsonify(data=template_folder.serialize()), 200


@template_folder_blueprint.route('/<uuid:template_folder_id>', methods=['DELETE'])
def delete_template_folder(service_id, template_folder_id):
    template_folder = dao_get_template_folder_by_id_and_service_id(template_folder_id, service_id)

    # don't allow deleting if there's anything in the folder (even if it's just more empty subfolders)
    if template_folder.subfolders or template_folder.templates:
        return jsonify(result='error', message='Folder is not empty'), 400

    dao_delete_template_folder(template_folder)

    return '', 204


@template_folder_blueprint.route('/contents', methods=['POST'])
@template_folder_blueprint.route('/<uuid:target_template_folder_id>/contents', methods=['POST'])
@transactional
def move_to_template_folder(service_id, target_template_folder_id=None):
    data = request.get_json()

    validate(data, post_move_template_folder_schema)

    if target_template_folder_id:
        target_template_folder = dao_get_template_folder_by_id_and_service_id(target_template_folder_id, service_id)
    else:
        target_template_folder = None

    for template_folder_id in data['folders']:
        try:
            template_folder = dao_get_template_folder_by_id_and_service_id(template_folder_id, service_id)
        except NoResultFound:
            msg = 'No folder found with id {} for service {}'.format(
                template_folder_id,
                service_id
            )
            raise InvalidRequest(msg, status_code=400)
        _validate_folder_move(target_template_folder, target_template_folder_id, template_folder, template_folder_id)

        template_folder.parent = target_template_folder

    for template_id in data['templates']:
        try:
            template = dao_get_template_by_id_and_service_id(template_id, service_id)
        except NoResultFound:
            msg = 'Could not move to folder: No template found with id {} for service {}'.format(
                template_id,
                service_id
            )
            raise InvalidRequest(msg, status_code=400)

        if template.archived:
            current_app.logger.info('Could not move to folder: Template {} is archived. (Skipping)'.format(
                template_id
            ))
        else:
            template.folder = target_template_folder
    return '', 204


def _validate_folder_move(target_template_folder, target_template_folder_id, template_folder, template_folder_id):
    if str(target_template_folder_id) == str(template_folder_id):
        msg = 'Could not move to folder to itself'
        raise InvalidRequest(msg, status_code=400)
    if target_template_folder and template_folder.is_parent_of(target_template_folder):
        msg = 'Could not move to folder: {} is an ancestor of target folder {}'.format(
            template_folder_id,
            target_template_folder_id
        )
        raise InvalidRequest(msg, status_code=400)
