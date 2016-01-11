import json
from datetime import datetime
from sqlalchemy.orm import load_only
from . import DAOException
from app import db
from app.models import Service


def save_model_service(service, update_dict=None):
    users_list = update_dict.get('users', []) if update_dict else getattr(service, 'users', [])
    if not users_list:
        error_msg = {'users': 'Missing data for required attribute'}
        raise DAOException(json.dumps(error_msg))
    if update_dict:
        del update_dict['id']
        del update_dict['users']
        db.session.query(Service).filter_by(id=service.id).update(update_dict)
    else:
        db.session.add(service)
    db.session.commit()


def get_model_services(service_id=None, user_id=None):
    # TODO need better mapping from function params to sql query.
    if user_id and service_id:
        return Service.query.filter(
            Service.users.any(id=user_id)).filter_by(id=service_id).one()
    elif service_id:
        return Service.query.filter_by(id=service_id).one()
    elif user_id:
        return Service.query.filter(Service.users.any(id=user_id)).all()
    return Service.query.all()
