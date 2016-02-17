import json

from app.dao import DAOException

from app import db
from app.models import Service


def save_model_service(service, update_dict=None):
    users_list = update_dict.get('users', []) if update_dict else getattr(service, 'users', [])
    if not users_list:
        error_msg = {'users': ['Missing data for required attribute']}
        raise DAOException(json.dumps(error_msg))
    if update_dict:
        # Make sure the update_dict doesn't contain conflicting
        update_dict.pop('id', None)
        update_dict.pop('users', None)
        # TODO optimize this algorithm
        for i, x in enumerate(service.users):
            if x not in users_list:
                service.users.remove(x)
            else:
                users_list.remove(x)
        for x in users_list:
            service.users.append(x)
        Service.query.filter_by(id=service.id).update(update_dict)
    else:
        db.session.add(service)
    db.session.commit()


def delete_model_service(service):
    db.session.delete(service)
    db.session.commit()


def get_model_services(service_id=None, user_id=None, _raise=True):
    # TODO need better mapping from function params to sql query.
    if user_id and service_id:
        return Service.query.filter(
            Service.users.any(id=user_id)).filter_by(id=service_id).one()
    elif service_id:
        result = Service.query.filter_by(id=service_id).one() if _raise else Service.query.filter_by(
            id=service_id).first()
        return result
    elif user_id:
        return Service.query.filter(Service.users.any(id=user_id)).all()
    return Service.query.all()
