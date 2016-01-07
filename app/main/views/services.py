from flask import jsonify
from app.main.dao.services_dao import (create_new_service, get_services)
from app.main.dao.users_dao import (get_users)
from .. import main


# TODO auth to be added.
@main.route('/service', methods=['POST'])
def create_service():
    return jsonify(result="created"), 201


# TODO auth to be added
@main.route('/service/<int:service_id>', method=['PUT'])
def update_service(service_id):
    return jsonify(result="updated")


# TODO auth to be added.
# Should be restricted by user, user id
# is pulled from the token
@main.route('/service/<int:service_id>', method=['GET'])
@main.route('/service', methods=['GET'])
def get_service(service_id=None):
    services = get_services
    return jsonify(
        data=services
    )


# TODO auth to be added
# auth should be allow for admin tokens only
@main.route('/user/<int:user_id>/service', method=['GET'])
@main.route('/user/<int:user_id>/service/<int:service_id>', method=['GET'])
def get_service_by_user_id(user_id, service_id=None):
    user = get_users(user_id=user_id)
    services = get_services(user, service_id=service_id)
    return jsonify(data=services)
