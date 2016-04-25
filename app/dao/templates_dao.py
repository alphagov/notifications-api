import uuid
from app import db
from app.models import (Template, Service)
from sqlalchemy import asc

from app.dao.dao_utils import (
    transactional,
    version_class
)


@transactional
@version_class(Template)
def dao_create_template(template):
    template.id = uuid.uuid4()  # must be set now so version history model can use same id
    db.session.add(template)


@transactional
@version_class(Template)
def dao_update_template(template):
    db.session.add(template)


def dao_get_template_by_id_and_service_id(template_id, service_id):
    return Template.query.filter_by(id=template_id, service_id=service_id).one()


def dao_get_template_by_id(template_id):
    return Template.query.filter_by(id=template_id).one()


def dao_get_all_templates_for_service(service_id):
    return Template.query.filter_by(
        service=Service.query.get(service_id)
    ).order_by(
        asc(Template.updated_at), asc(Template.created_at)
    ).all()
