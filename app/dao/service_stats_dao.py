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


def _update_service_stats_count(dimensions: ServiceStatsDimensions, delta: int) -> None:
    if delta == 0:
        return

    dimension_values = {
        "service_id": dimensions["service_id"],
        "template_id": dimensions["template_id"],
        "notification_type": dimensions["notification_type"],
        "notification_status": dimensions["notification_status"],
    }
    filters = (
        ServiceStats.service_id == dimension_values["service_id"],
        ServiceStats.template_id == dimension_values["template_id"],
        ServiceStats.notification_type == dimension_values["notification_type"],
        ServiceStats.notification_status == dimension_values["notification_status"],
    )

    if delta > 0:
        stmt = insert(ServiceStats).values(
            id=uuid.uuid4(),
            **dimension_values,
            count=delta,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uix_service_stats_dimensions",
            set_={
                "count": ServiceStats.count + delta,
            },
        )
        db.session.execute(stmt)
    else:
        (
            db.session.query(ServiceStats)
            .filter(*filters)
            .update(
                {
                    "count": func.greatest(ServiceStats.count + delta, 0),
                },
                synchronize_session=False,
            )
        )


def apply_service_stats_delta(dimensions: ServiceStatsDimensions, delta: int) -> None:
    _update_service_stats_count(dimensions, delta)


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