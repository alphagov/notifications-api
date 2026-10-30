from datetime import date, datetime
from typing import TypedDict
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from app import db
from app.models import FactNotificationStatusLive


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
