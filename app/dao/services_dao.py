import json
from datetime import datetime

from sqlalchemy.orm import load_only
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Service


# Should I use SQLAlchemyError?
class DAOException(SQLAlchemyError):
    pass


def create_model_service(service):
    users_list = getattr(service, 'users', [])
    if not users_list:
        error_msg = {'users': 'Missing data for required attribute'}
        raise DAOException(json.dumps(error_msg))
    db.session.add(service)
    db.session.commit()


def get_model_services(service_id=None, user_id=None):
    # TODO need better mapping from function params to sql query.
    if user_id and service_id:
        return Service.query.filter(
            Service.users.any(id=user_id), id=service_id).one()
    elif service_id:
        return Service.query.filter_by(id=service_id).one()
    elif user_id:
        return Service.query.filter(Service.users.any(id=user_id)).all()
    return Service.query.all()
