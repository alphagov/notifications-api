from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import raiseload, selectinload
from sqlalchemy.orm.exc import NoResultFound

from app.dao.dao_utils import autocommit
from app.dao.service_user_dao import (
    dao_get_active_service_users,
    dao_get_service_user,
)
from app.dao.template_folder_dao import (
    dao_create_template_folder,
    dao_delete_template_folder,
    dao_get_template_folder_by_id_and_service_id,
    dao_update_template_folder,
)
from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.errors import InvalidRequest, register_errors
from app.models import Service, TemplateFolder
from app.schema_validation import validate
from app.template_folder.template_folder_schema import (
    post_create_template_folder_schema,
    post_move_template_folder_schema,
    post_update_template_folder_schema,
)

template_folder_blueprint = Blueprint(
    "template_folder", __name__, url_prefix="/service/<uuid:service_id>/template-folder"
)
register_errors(template_folder_blueprint)


@template_folder_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    if "template_folder_parent_id_fkey" in str(exc):
        return jsonify(result="error", message="parent_id not found"), 400

    raise


@template_folder_blueprint.route("", methods=["GET"])
def get_template_folders_for_service(service_id):
    service = (
        Service.query.filter_by(id=service_id)
        .options(raiseload("users"), selectinload("all_template_folders").options(selectinload("users")))
        .one()
    )

    template_folders = [o.serialize() for o in service.all_template_folders]
    return jsonify(template_folders=template_folders)


@template_folder_blueprint.route("", methods=["POST"])
def create_template_folder(service_id):
    data = request.get_json()

    validate(data, post_create_template_folder_schema)
    if data.get("parent_id") is not None:
        try:
            parent_folder = dao_get_template_folder_by_id_and_service_id(data["parent_id"], service_id)
            users_with_permission = parent_folder.users
        except NoResultFound as e:
            raise InvalidRequest("parent_id not found", status_code=400) from e
    else:
        users_with_permission = dao_get_active_service_users(service_id)
    template_folder = TemplateFolder(
        service_id=service_id,
        name=data["name"].strip(),
        parent_id=data["parent_id"],
        users=users_with_permission,
    )

    dao_create_template_folder(template_folder)

    return jsonify(data=template_folder.serialize()), 201


@template_folder_blueprint.route("/<uuid:template_folder_id>", methods=["POST"])
def update_template_folder(service_id, template_folder_id):
    data = request.get_json()

    validate(data, post_update_template_folder_schema)

    template_folder = dao_get_template_folder_by_id_and_service_id(template_folder_id, service_id)
    template_folder.name = data["name"]
    if "users_with_permission" in data:
        template_folder.users = [dao_get_service_user(user_id, service_id) for user_id in data["users_with_permission"]]

    dao_update_template_folder(template_folder)

    return jsonify(data=template_folder.serialize()), 200


@template_folder_blueprint.route("/<uuid:template_folder_id>", methods=["DELETE"])
def delete_template_folder(service_id, template_folder_id):
    template_folder = dao_get_template_folder_by_id_and_service_id(template_folder_id, service_id)

    # don't allow deleting if there's anything in the folder (even if it's just more empty subfolders)
    if template_folder.subfolders or template_folder.templates:
        return jsonify(result="error", message="Folder is not empty"), 400

    dao_delete_template_folder(template_folder)

    return "", 204


@template_folder_blueprint.route("/contents", methods=["POST"])
@template_folder_blueprint.route("/<uuid:target_template_folder_id>/contents", methods=["POST"])
@autocommit
def move_to_template_folder(service_id, target_template_folder_id=None):
    data = request.get_json()

    validate(data, post_move_template_folder_schema)

    if target_template_folder_id:
        target_template_folder = dao_get_template_folder_by_id_and_service_id(target_template_folder_id, service_id)
    else:
        target_template_folder = None

    for template_folder_id in data["folders"]:
        try:
            template_folder = dao_get_template_folder_by_id_and_service_id(template_folder_id, service_id)
        except NoResultFound as e:
            msg = f"No folder found with id {template_folder_id} for service {service_id}"
            raise InvalidRequest(msg, status_code=400) from e
        _validate_folder_move(target_template_folder, target_template_folder_id, template_folder, template_folder_id)

        template_folder.parent = target_template_folder

    for template_id in data["templates"]:
        try:
            template = dao_get_template_by_id_and_service_id(template_id, service_id)
        except NoResultFound as e:
            msg = f"Could not move to folder: No template found with id {template_id} for service {service_id}"
            raise InvalidRequest(msg, status_code=400) from e

        if template.archived:
            current_app.logger.info("Could not move to folder: Template %s is archived. (Skipping)", template_id)
        else:
            template.folder = target_template_folder
    return "", 204


def _validate_folder_move(target_template_folder, target_template_folder_id, template_folder, template_folder_id):
    if str(target_template_folder_id) == str(template_folder_id):
        msg = "You cannot move a folder to itself"
        raise InvalidRequest(msg, status_code=400)
    if target_template_folder and template_folder.is_parent_of(target_template_folder):
        msg = "You cannot move a folder to one of its subfolders"
        raise InvalidRequest(msg, status_code=400)
