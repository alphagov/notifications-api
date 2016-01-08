from datetime import datetime

from sqlalchemy.orm import load_only

from app import db
from app.models import Service


def create_service(service_name,
                   user,
                   limit=1000,
                   active=False,
                   restricted=True):
    service = Service(name=service_name,
                      created_at=datetime.now(),
                      limit=limit,
                      active=active,
                      restricted=restricted)
    db.session.add(service)
    service.users.append(user)
    db.session.commit()
    return service.id


def get_services(service_id=None, user_id=None):
    # TODO need better mapping from function params to sql query.
    if user_id and service_id:
        return Service.query.filter(Service.users.any(id=user_id), id=service_id).one()
    elif service_id:
        return Service.query.filter_by(id=service_id).one()
    elif user_id:
        return Service.query.filter(Service.users.any(id=user_id)).all()
    return Service.query.all()
