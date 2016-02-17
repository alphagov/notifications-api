from app import db
from app.models import (Template, Service)


def save_model_template(template, update_dict=None):
    if update_dict:
        update_dict.pop('id', None)
        service = update_dict.pop('service')
        Template.query.filter_by(id=template.id).update(update_dict)
        template.service = service
    else:
        db.session.add(template)
    db.session.commit()


def delete_model_template(template):
    db.session.delete(template)
    db.session.commit()


def get_model_templates(template_id=None, service_id=None):
    # TODO need better mapping from function params to sql query.
    if template_id and service_id:
        return Template.query.filter_by(
            id=template_id, service_id=service_id).one()
    elif template_id:
        return Template.query.filter_by(id=template_id).one()
    elif service_id:
        return Template.query.filter_by(service=Service.query.get(service_id)).all()
    return Template.query.all()
