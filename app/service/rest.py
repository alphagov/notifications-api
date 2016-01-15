from datetime import datetime

from flask import (jsonify, request, current_app)
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao import DAOException
from app.dao.services_dao import (
    save_model_service, get_model_services, delete_model_service)
from app.dao.templates_dao import (
    save_model_template, get_model_templates, delete_model_template)
from app.dao.tokens_dao import (save_model_token, get_model_tokens, get_unsigned_token)
from app.models import Token
from app.schemas import (
    services_schema, service_schema, template_schema)

from flask import Blueprint
service = Blueprint('service', __name__)


@service.route('/', methods=['POST'])
def create_service():
    # TODO what exceptions get passed from schema parsing?
    service, errors = service_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    # I believe service is already added to the session but just needs a
    # db.session.commit
    try:
        save_model_service(service)
        save_model_token(Token(service_id=service.id))
    except DAOException as e:
        return jsonify(result="error", message=str(e)), 400
    return jsonify(data=service_schema.dump(service).data, token=get_unsigned_token(service.id)), 201


# TODO auth to be added
@service.route('/<int:service_id>', methods=['PUT', 'DELETE'])
def update_service(service_id):
    try:
        service = get_model_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service not found"), 404
    if request.method == 'DELETE':
        status_code = 202
        delete_model_service(service)
    else:
        status_code = 200
        # TODO there has got to be a better way to do the next three lines
        upd_serv, errors = service_schema.load(request.get_json())
        if errors:
            return jsonify(result="error", message=errors), 400
        update_dict, errors = service_schema.dump(upd_serv)
        # TODO FIX ME
        # Remove update_service model which is added to db.session
        db.session.rollback()
        try:
            save_model_service(service, update_dict=update_dict)
        except DAOException as e:
            return jsonify(result="error", message=str(e)), 400
    return jsonify(data=service_schema.dump(service).data), status_code


# TODO auth to be added.
@service.route('/<int:service_id>', methods=['GET'])
@service.route('/', methods=['GET'])
def get_service(service_id=None):
    try:
        services = get_model_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service not found"), 404
    data, errors = services_schema.dump(services) if isinstance(services, list) else service_schema.dump(services)
    return jsonify(data=data)


# TODO auth to be added
@service.route('/<int:service_id>/token/renew', methods=['POST'])
def renew_token(service_id=None):
    try:
        get_model_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service not found"), 404

    try:
        service_token = get_model_tokens(service_id=service_id, raise_=False)
        if service_token:
            # expire existing token
            save_model_token(service_token, update_dict={'id': service_token.id, 'expiry_date': datetime.now()})
        # create a new one
        save_model_token(Token(service_id=service_id))
    except DAOException as e:
        return jsonify(result='error', message=str(e)), 400
    unsigned_token = get_unsigned_token(service_id)
    return jsonify(data=unsigned_token), 201


@service.route('/<int:service_id>/token/revoke', methods=['POST'])
def revoke_token(service_id):
    try:
        get_model_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service not found"), 404

    service_token = get_model_tokens(service_id=service_id, raise_=False)
    if service_token:
        save_model_token(service_token, update_dict={'id': service_token.id, 'expiry_date': datetime.now()})
    return jsonify(), 202


# TODO auth to be added.
@service.route('/<int:service_id>/template/', methods=['POST'])
def create_template(service_id):
    try:
        service = get_model_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service not found"), 404
    template, errors = template_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    template.service = service
    # I believe service is already added to the session but just needs a
    # db.session.commit
    save_model_template(template)
    return jsonify(data=template_schema.dump(template).data), 201


# TODO auth to be added
@service.route('/<int:service_id>/template/<int:template_id>', methods=['PUT', 'DELETE'])
def update_template(service_id, template_id):
    try:
        service = get_model_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service not found"), 404
    try:
        template = get_model_templates(template_id=template_id)
    except DataError:
        return jsonify(result="error", message="Invalid template id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Template not found"), 404
    if request.method == 'DELETE':
        status_code = 202
        delete_model_template(template)
    else:
        status_code = 200
        # TODO there has got to be a better way to do the next three lines
        upd_temp, errors = template_schema.load(request.get_json())
        if errors:
            return jsonify(result="error", message=errors), 400
        upd_temp.service = service
        update_dict, errors = template_schema.dump(upd_temp)
        # TODO FIX ME
        # Remove update_temp model which is added to db.session
        db.session.rollback()
        try:
            save_model_template(template, update_dict=update_dict)
        except DAOException as e:
            return jsonify(result="error", message=str(e)), 400
    return jsonify(data=template_schema.dump(template).data), status_code
