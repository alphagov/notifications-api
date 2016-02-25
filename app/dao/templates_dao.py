from app import db
from app.models import (Template, Service)
from sqlalchemy import asc


def dao_create_template(template):
    db.session.add(template)
    db.session.commit()


def dao_update_template(template):
    db.session.add(template)
    db.session.commit()


def dao_get_template_by_id_and_service_id(template_id, service_id):
    return Template.query.filter_by(id=template_id, service_id=service_id).first()


def dao_get_template_by_id(template_id):
    return Template.query.filter_by(id=template_id).first()


def dao_get_all_templates_for_service(service_id):
    return Template.query.filter_by(service=Service.query.get(service_id)).order_by(asc(Template.created_at)).all()
