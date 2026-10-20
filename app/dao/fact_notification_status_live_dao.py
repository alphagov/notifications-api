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


def apply_notification_status_live_change(dimensions: NotificationStatusLiveDimensions, change_count: int) -> None:
    _update_notification_status_live_count(dimensions, change_count)


def _update_notification_status_live_count(dimensions: NotificationStatusLiveDimensions, change_count: int) -> None:
    if change_count == 0:
        return

    dimension_values = {
        "bst_date": dimensions["bst_date"],
        "service_id": dimensions["service_id"],
        "template_id": dimensions["template_id"],
        "job_id": dimensions["job_id"],
        "key_type": dimensions["key_type"],
        "notification_type": dimensions["notification_type"],
        "notification_status": dimensions["notification_status"],
    }

    stmt = insert(FactNotificationStatusLive).values(
        **dimension_values,
        notification_count=change_count,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="ft_notification_status_live_pkey",
        set_={
            "notification_count": FactNotificationStatusLive.notification_count + change_count,
            "updated_at": datetime.utcnow(),
        },
    )

    db.session.execute(stmt)

    db.session.commit()
