from flask import (
    jsonify,
    request,
    Blueprint
)

from app.schemas import permission_schema

from app.errors import (
    register_errors,
    InvalidData
)

from app.dao.permissions_dao import permission_dao

permission = Blueprint('permission', __name__)
register_errors(permission)


@permission.route('', methods=['GET'])
def get_permissions():
    data, errors = permission_schema.dump(
        permission_dao.get_query(filter_by_dict=request.args), many=True)
    if errors:
        raise InvalidData(errors, status_code=500)
    return jsonify(data=data)


@permission.route('/<permission_id>', methods=['GET'])
def get_permission(permission_id):
    inst = permission_dao.get_query(filter_by_dict={'id': permission_id}).one()
    data, errors = permission_schema.dump(inst)
    if errors:
        raise InvalidData(errors, status_code=500)
    return jsonify(data=data)
