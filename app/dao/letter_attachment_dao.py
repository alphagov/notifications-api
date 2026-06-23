import datetime
from uuid import UUID

from flask import current_app
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, scoped_session

from app import db
from app.models import LetterAttachment, Template
from app.utils import retryable_query


@retryable_query()
def dao_get_archived_letter_attachments_older_than(
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
            session.query(LetterAttachment.archived_at).filter(LetterAttachment.id == older_than).scalar()
        )

        if last_archived_at is None:
            return []

        next_page_filter.append(
            or_(
                LetterAttachment.archived_at > last_archived_at,
                and_(
                    LetterAttachment.archived_at == last_archived_at,
                    LetterAttachment.id > older_than,
                ),
            ),
        )

    return (
        session.query(LetterAttachment, Template.service_id)
        .join(Template, Template.letter_attachment_id == LetterAttachment.id)
        .filter(
            LetterAttachment.archived_at.is_not(None),
            *(() if archived_after is None else (LetterAttachment.archived_at >= archived_after,)),
            LetterAttachment.archived_at <= archived_before,
            *next_page_filter,
        )
        .order_by(
            LetterAttachment.archived_at.asc(),
            LetterAttachment.id.asc(),
        )
        .limit(page_size)
        .all()
    )
