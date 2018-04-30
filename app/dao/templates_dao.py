from datetime import datetime
import uuid

from sqlalchemy import asc, desc

from app import db
from app.models import (
    Template,
    TemplateHistory,
    TemplateRedacted
)
from app.dao.dao_utils import (
    transactional,
    version_class
)


@transactional
@version_class(Template, TemplateHistory)
def dao_create_template(template):
    template.id = uuid.uuid4()  # must be set now so version history model can use same id
    template.archived = False

    template.template_redacted = TemplateRedacted(
        template=template,
        redact_personalisation=False,
        updated_by=template.created_by
    )

    db.session.add(template)


@transactional
@version_class(Template, TemplateHistory)
def dao_update_template(template):
    db.session.add(template)


@transactional
def dao_update_template_reply_to(template_id, reply_to):
    Template.query.filter_by(id=template_id).update(
        {"service_letter_contact_id": reply_to,
         "updated_at": datetime.utcnow(),
         "version": Template.version + 1,
         }
    )
    template = Template.query.filter_by(id=template_id).one()

    history = TemplateHistory(**
                              {
                                  "id": template.id,
                                  "name": template.name,
                                  "template_type": template.template_type,
                                  "created_at": template.created_at,
                                  "updated_at": template.updated_at,
                                  "content": template.content,
                                  "service_id": template.service_id,
                                  "subject": template.subject,
                                  "created_by_id": template.created_by_id,
                                  "version": template.version,
                                  "archived": template.archived,
                                  "process_type": template.process_type,
                                  "service_letter_contact_id": template.service_letter_contact_id
                              })
    db.session.add(history)
    return template


@transactional
def dao_redact_template(template, user_id):
    template.template_redacted.redact_personalisation = True
    template.template_redacted.updated_at = datetime.utcnow()
    template.template_redacted.updated_by_id = user_id
    db.session.add(template.template_redacted)


def dao_get_template_by_id_and_service_id(template_id, service_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(
            id=template_id,
            hidden=False,
            service_id=service_id,
            version=version).one()
    return Template.query.filter_by(id=template_id, hidden=False, service_id=service_id).one()


def dao_get_template_by_id(template_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(
            id=template_id,
            version=version).one()
    return Template.query.filter_by(id=template_id).one()


def dao_get_all_templates_for_service(service_id, template_type=None):
    if template_type is not None:
        return Template.query.filter_by(
            service_id=service_id,
            template_type=template_type,
            hidden=False,
            archived=False
        ).order_by(
            asc(Template.name),
            asc(Template.template_type),
        ).all()

    return Template.query.filter_by(
        service_id=service_id,
        hidden=False,
        archived=False
    ).order_by(
        asc(Template.name),
        asc(Template.template_type),
    ).all()


def dao_get_template_versions(service_id, template_id):
    return TemplateHistory.query.filter_by(
        service_id=service_id, id=template_id,
        hidden=False,
    ).order_by(
        desc(TemplateHistory.version)
    ).all()


def dao_get_multiple_template_details(template_ids):
    query = db.session.query(
        Template.id,
        Template.template_type,
        Template.name,
        Template.is_precompiled_letter
    ).filter(
        Template.id.in_(template_ids)
    ).order_by(
        Template.name
    )

    return query.all()
