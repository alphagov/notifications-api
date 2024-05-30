from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import asc, desc

from app import db
from app.constants import LETTER_TYPE, SECOND_CLASS
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.dao.users_dao import get_user_by_id
from app.models import Template, TemplateHistory, TemplateRedacted


@autocommit
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_create_template(template):
    template.archived = False

    redacted_dict = {
        "template": template,
        "redact_personalisation": False,
    }
    if template.created_by:
        redacted_dict.update({"updated_by": template.created_by})
    else:
        redacted_dict.update({"updated_by_id": template.created_by_id})

    template.template_redacted = TemplateRedacted(**redacted_dict)

    db.session.add(template)


@autocommit
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_update_template(template):
    db.session.add(template)


@autocommit
def dao_redact_template(template, user_id):
    template.template_redacted.redact_personalisation = True
    template.template_redacted.updated_at = datetime.now(UTC).replace(tzinfo=None)
    template.template_redacted.updated_by_id = user_id
    db.session.add(template.template_redacted)


def dao_get_template_by_id_and_service_id(template_id, service_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(
            id=template_id, hidden=False, service_id=service_id, version=version
        ).one()
    return Template.query.filter_by(id=template_id, hidden=False, service_id=service_id).one()


def dao_get_template_by_id(template_id, version=None):
    if version is not None:
        return TemplateHistory.query.filter_by(id=template_id, version=version).one()
    return Template.query.filter_by(id=template_id).one()


def dao_get_all_templates_for_service(service_id, template_type=None):
    if template_type is not None:
        return (
            Template.query.filter_by(service_id=service_id, template_type=template_type, hidden=False, archived=False)
            .order_by(
                asc(Template.name),
                asc(Template.template_type),
            )
            .all()
        )

    return (
        Template.query.filter_by(service_id=service_id, hidden=False, archived=False)
        .order_by(
            asc(Template.name),
            asc(Template.template_type),
        )
        .all()
    )


def dao_get_template_versions(service_id, template_id):
    return (
        TemplateHistory.query.filter_by(
            service_id=service_id,
            id=template_id,
            hidden=False,
        )
        .order_by(desc(TemplateHistory.version))
        .all()
    )


def get_precompiled_letter_template(service_id):
    template = Template.query.filter_by(service_id=service_id, template_type=LETTER_TYPE, hidden=True).first()
    if template is not None:
        return template

    template = Template(
        name="Pre-compiled PDF",
        created_by=get_user_by_id(current_app.config["NOTIFY_USER_ID"]),
        service_id=service_id,
        template_type=LETTER_TYPE,
        hidden=True,
        subject="Pre-compiled PDF",
        content="",
        postage=SECOND_CLASS,
    )

    dao_create_template(template)

    return template
