import uuid
from typing import TypedDict
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app import db
from app.models import ServiceStats


class ServiceStatsDimensions(TypedDict):
    service_id: UUID
    template_id: UUID
    notification_type: str
    notification_status: str


def _increment_service_stats_count(dimensions: ServiceStatsDimensions, increment_by: int) -> None:
    stmt = insert(ServiceStats).values(
        id=uuid.uuid4(),
        service_id=dimensions["service_id"],
        template_id=dimensions["template_id"],
        notification_type=dimensions["notification_type"],
        notification_status=dimensions["notification_status"],
        count=increment_by,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uix_service_stats_dimensions",
        set_={
            "count": ServiceStats.count + increment_by,
        },
    )
    db.session.execute(stmt)


def _decrement_service_stats_count(dimensions: ServiceStatsDimensions, decrement_by: int) -> None:
    (
        db.session.query(ServiceStats)
        .filter(
            ServiceStats.service_id == dimensions["service_id"],
            ServiceStats.template_id == dimensions["template_id"],
            ServiceStats.notification_type == dimensions["notification_type"],
            ServiceStats.notification_status == dimensions["notification_status"],
        )
        .update(
            {
                "count": func.greatest(ServiceStats.count - decrement_by, 0),
            },
            synchronize_session=False,
        )
    )


def apply_service_stats_delta(dimensions: ServiceStatsDimensions, delta: int) -> None:
    if delta > 0:
        _increment_service_stats_count(dimensions, increment_by=delta)
    elif delta < 0:
        _decrement_service_stats_count(dimensions, decrement_by=abs(delta))


def dao_fetch_stats_for_service(service_id: UUID) -> list[ServiceStats]:
    """
    Fetch service stats for a specific service.

    Args:
        service_id: UUID of the service to fetch stats for

    Returns:
        List of ServiceStats records for the specified service
    """
    if not service_id:
        return []

    return db.session.query(ServiceStats).filter(ServiceStats.service_id == service_id).all()