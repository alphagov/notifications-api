from datetime import datetime
import uuid

from sqlalchemy import asc, desc
from sqlalchemy.sql.expression import bindparam

from app import db
from app.models import (Template, TemplateHistory, TemplateRedacted)
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
def dao_redact_template(template, user_id):
    template.template_redacted.redact_personalisation = True
    template.template_redacted.updated_at = datetime.utcnow()
    template.template_redacted.updated_by_id = user_id
    db.session.add(template.template_redacted)


def dao_get_template_by_id_and_service_id(template_id, service_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(
            id=template_id,
            service_id=service_id,
            version=version).one()
    return Template.query.filter_by(id=template_id, service_id=service_id).one()


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
            archived=False
        ).order_by(
            asc(Template.name),
            asc(Template.template_type),
        ).all()

    return Template.query.filter_by(
        service_id=service_id,
        archived=False
    ).order_by(
        asc(Template.name),
        asc(Template.template_type),
    ).all()


def dao_get_template_versions(service_id, template_id):
    return TemplateHistory.query.filter_by(
        service_id=service_id, id=template_id
    ).order_by(
        desc(TemplateHistory.version)
    ).all()


def dao_get_templates_for_cache(cache):
    if not cache or len(cache) == 0:
        return []

    # First create a subquery that is a union select of the cache values
    # Then join templates to the subquery
    cache_queries = [
        db.session.query(bindparam("template_id" + str(i),
                                   uuid.UUID(template_id.decode())).label('template_id'),
                         bindparam("count" + str(i), int(count.decode())).label('count'))
        for i, (template_id, count) in enumerate(cache)]
    cache_subq = cache_queries[0].union(*cache_queries[1:]).subquery()
    query = db.session.query(Template.id.label('template_id'),
                             Template.template_type,
                             Template.name,
                             cache_subq.c.count.label('count')
                             ).join(cache_subq,
                                    Template.id == cache_subq.c.template_id
                                    ).order_by(Template.name)

    return query.all()
