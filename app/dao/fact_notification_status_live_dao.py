from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import TypedDict
from uuid import UUID

from sqlalchemy import Row, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, scoped_session

from app import db
from app.constants import KEY_TYPE_TEST
from app.models import FactNotificationStatusLive, Template
from app.utils import midnight_n_days_ago, retryable_query


class NotificationStatusLiveDimensions(TypedDict):
    bst_date: date
    service_id: UUID
    template_id: UUID
    job_id: UUID
    key_type: str
    notification_type: str
    notification_status: str
    notification_count: int


def upsert_notification_status_live_counts(count_changes: list[NotificationStatusLiveDimensions]) -> None:
    changes = [dimensions for dimensions in count_changes if dimensions["notification_count"] != 0]

    if not changes:
        return

    stmt = insert(FactNotificationStatusLive).values(changes)
    stmt = stmt.on_conflict_do_update(
        constraint="ft_notification_status_live_pkey",
        set_={
            "notification_count": FactNotificationStatusLive.notification_count + stmt.excluded.notification_count,
            "updated_at": datetime.utcnow(),
        },
    )

    db.session.execute(stmt)
    db.session.commit()


def fetch_notification_status_live_for_service_for_today_and_7_previous_days(
    service_id,
    by_template=False,
    limit_days=7,
    chunk_timedelta=timedelta(minutes=30),
    inner_retry_attempts=0,
    session=db.session,
):
    return _fetch_notification_status_for_service_for_today_and_7_previous_days_fact_query(
        service_id,
        by_template,
        limit_days,
        session=session,
        retry_attempts=inner_retry_attempts,  # type: ignore
    )


@retryable_query()
def _fetch_notification_status_for_service_for_today_and_7_previous_days_fact_query(
    service_id: UUID | str, by_template: bool, limit_days: int, session: Session | scoped_session = db.session
) -> Sequence[Row]:
    start_dt = midnight_n_days_ago(limit_days)
    query = session.query(
        *(
            [
                Template.name.label("template_name"),
                Template.is_precompiled_letter.label("is_precompiled_letter"),
                FactNotificationStatusLive.template_id.label("template_id"),
            ]
            if by_template
            else []
        ),
        FactNotificationStatusLive.notification_type.label("notification_type"),
        FactNotificationStatusLive.notification_status.label("status"),
        func.sum(FactNotificationStatusLive.notification_count).label("count"),
    )
    if by_template:
        # outer join so counts are still returned (with null template fields) if the template can't be found
        query = query.outerjoin(Template, Template.id == FactNotificationStatusLive.template_id)

    return (
        query.filter(
            FactNotificationStatusLive.service_id == service_id,
            FactNotificationStatusLive.bst_date >= start_dt,
            FactNotificationStatusLive.key_type != KEY_TYPE_TEST,
        )
        .group_by(
            *(
                [Template.name, Template.is_precompiled_letter, FactNotificationStatusLive.template_id]
                if by_template
                else []
            ),
            FactNotificationStatusLive.notification_type,
            FactNotificationStatusLive.notification_status,
        )
        .all()
    )
