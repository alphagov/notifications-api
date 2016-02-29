
from flask import (jsonify, request, abort, Blueprint, current_app)
from app.schemas import permission_schema
from app.errors import register_errors
from app.dao.permissions_dao import permission_dao

permission = Blueprint('permission', __name__)
register_errors(permission)


@permission.route('', methods=['GET'])
def get_permissions():
    data, errors = permission_schema.dump(
        permission_dao.get_query(filter_by_dict=request.args), many=True)
    if errors:
        abort(500, errors)
    return jsonify(data=data)


@permission.route('/<permission_id>', methods=['GET'])
def get_permission(permission_id):
    inst = permission_dao.get_query(filter_by_dict={'id': permission_id}).first()
    if not inst:
        abort(404, 'Permission not found for id: {permission_id}'.format(permission_id))
    data, errors = permission_schema.dump(inst)
    if errors:
        abort(500, errors)
    return jsonify(data=data)


@permission.route('', methods=['POST'])
def create_permission():
    inst, errors = permission_schema.load(request.get_json())
    if errors:
        abort(400, errors)
    # Commit instance to the database
    permission_dao.create_instance(inst)
    data, errors = permission_schema.dump(inst)
    if errors:
        abort(500, errors)
    return jsonify(data=data), 201


@permission.route('/<permission_id>', methods=['DELETE'])
def delete_permission(permission_id):
    inst = permission_dao.get_query(filter_by_dict={'id': permission_id}).first()
    if not inst:
        abort(404, 'Permission not found for id: {permission_id}'.format(permission_id))
    # Generate response first
    data, errors = permission_schema.dump(inst)
    permission_dao.delete_instance(inst)
    if errors:
        abort(500, errors)
    return jsonify(data=data), 200
