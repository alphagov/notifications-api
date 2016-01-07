from datetime import datetime

from sqlalchemy.orm import load_only

from app import db
from app.models import Service


def create_new_service(service_name,
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


def get_services(user, service_id=None):
    if service_id:
        return Service.query.filter_by(user=user, service_id=service_id).one()
    return Service.query.filter_by(user=user).all()
