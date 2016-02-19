import json
from . import DAOException
from app import db
from app.models import Service
from sqlalchemy import asc


def dao_fetch_all_services():
    return Service.query.order_by(asc(Service.created_at)).all()


def dao_fetch_service_by_id(service_id):
    return Service.query.filter_by(id=service_id).first()


def dao_fetch_all_services_by_user(user_id):
    return Service.query.filter(Service.users.any(id=user_id)).order_by(asc(Service.created_at)).all()


def dao_fetch_service_by_id_and_user(service_id, user_id):
    return Service.query.filter(Service.users.any(id=user_id)).filter_by(id=service_id).first()


def dao_create_service(service, user):
    service.users.append(user)
    db.session.add(service)
    db.session.commit()


def dao_update_service(service):
    db.session.add(service)
    db.session.commit()


def dao_add_user_to_service(service, user):
    service.users.append(user)
    db.session.add(service)
    db.session.commit()


def dao_remove_user_from_service(service, user):
    service.users.remove(user)
    db.session.add(service)
    db.session.commit()
