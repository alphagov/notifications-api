import datetime
from itertools import chain
from uuid import UUID

from flask import current_app
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, scoped_session

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.models import Template, TemplateEmailFile, TemplateEmailFileHistory, TemplateHistory
from app.utils import retryable_query


@autocommit
def dao_create_pending_template_email_file(template_email_file: TemplateEmailFile):
    template = Template.query.get(template_email_file.template_id)
    template_email_file.template_version = template.version
    template_email_file.pending = True
    db.session.add(template_email_file)


@autocommit
@version_class(
    VersionOptions(TemplateEmailFile, history_class=TemplateEmailFileHistory),
)
def dao_create_template_email_file(template_email_file: TemplateEmailFile):
    template = Template.query.get(template_email_file.template_id)
    template_email_file.template_version = template.version
    db.session.add(template_email_file)


@autocommit
def dao_get_template_email_files_by_template_id(template_id, template_version=None):
    if template_version:
        query = (
            select(TemplateEmailFileHistory)
            .where(TemplateEmailFileHistory.template_id == template_id)
            .where(TemplateEmailFileHistory.template_version <= template_version)
            .where(TemplateEmailFileHistory.pending.is_(False))
            .order_by(TemplateEmailFileHistory.id)
            .order_by(TemplateEmailFileHistory.version.desc())
            .distinct(TemplateEmailFileHistory.id)
        )
        # prune archived after the fact
        return list(filter(lambda x: not x.archived_at, list(chain.from_iterable(db.session.execute(query).all()))))
    return TemplateEmailFile.query.filter(
        TemplateEmailFile.template_id == template_id,
        TemplateEmailFile.archived_at.is_(None),
        TemplateEmailFile.pending.is_(False),
    ).all()


@autocommit
def dao_get_template_email_file_by_id(template_email_file_id):
    return TemplateEmailFile.query.filter(TemplateEmailFile.id == template_email_file_id).one()


@retryable_query()
def dao_get_archived_template_email_files_older_than(
    session: Session | scoped_session = db.session,
    *,
    archived_before: datetime.datetime,
    archived_after: datetime.datetime | None = None,
    page_size: int | None = None,
    older_than: UUID | None = None,
):
    if page_size is None:
        page_size = current_app.config.get("API_PAGE_SIZE")

    next_page_filter = []
    if older_than is not None:
        last_archived_at = (
            session.query(TemplateEmailFile.archived_at).filter(TemplateEmailFile.id == older_than).scalar()
        )

        if last_archived_at is None:
            return []

        next_page_filter.append(
            or_(
                TemplateEmailFile.archived_at > last_archived_at,
                and_(
                    TemplateEmailFile.archived_at == last_archived_at,
                    TemplateEmailFile.id > older_than,
                ),
            ),
        )

    return (
        session.query(TemplateEmailFile, Template.service_id)
        .join(Template, Template.id == TemplateEmailFile.template_id)
        .filter(
            TemplateEmailFile.archived_at.is_not(None),
            *(() if archived_after is None else (TemplateEmailFile.archived_at >= archived_after,)),
            TemplateEmailFile.archived_at <= archived_before,
            *next_page_filter,
        )
        .order_by(
            TemplateEmailFile.archived_at.asc(),
            TemplateEmailFile.id.asc(),
        )
        .limit(page_size)
        .all()
    )


@autocommit
@version_class(
    VersionOptions(TemplateEmailFile, history_class=TemplateEmailFileHistory),
    VersionOptions(Template, history_class=TemplateHistory),
)
def dao_update_template_email_file(template_email_file: TemplateEmailFile):
    template = Template.query.get(template_email_file.template_id)
    template.updated_at = datetime.datetime.utcnow()
    template_email_file.template_version = template.version + 1
    db.session.add(template_email_file)
    db.session.add(template)


@autocommit
def dao_update_pending_template_email_file(template_email_file: TemplateEmailFile):
    db.session.add(template_email_file)


@autocommit
@version_class(
    VersionOptions(TemplateEmailFile, history_class=TemplateEmailFileHistory),
)
def dao_make_pending_template_email_file_live(template_email_file: TemplateEmailFile):
    template = Template.query.get(template_email_file.template_id)
    template_email_file.template_version = template.version
    db.session.add(template_email_file)


@autocommit
@version_class(
    VersionOptions(TemplateEmailFile, history_class=TemplateEmailFileHistory),
)
def dao_archive_template_email_file(file_to_archive, archived_by_id, template_version):
    if not file_to_archive.archived_at:
        file_to_archive.archived_at = datetime.datetime.utcnow()
        file_to_archive.archived_by_id = archived_by_id
        file_to_archive.template_version = template_version
        db.session.add(file_to_archive)
