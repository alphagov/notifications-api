import uuid
from typing import TypedDict
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app import db
from app.models import FactServiceStats


class ServiceStatsDimensions(TypedDict):
    service_id: UUID
    template_id: UUID
    notification_type: str
    notification_status: str


# 1. Public write API used by callers to apply a single aggregated delta into
# service statistics for a specific dimensions tuple.
def apply_service_stats_delta(dimensions: ServiceStatsDimensions, delta: int) -> None:
    _update_service_stats_count(dimensions, delta)


# 2. Internal persistence routine that applies the delta with UPSERT behavior for
# positive changes and bounded decrement behavior for negative changes.
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
        FactServiceStats.service_id == dimension_values["service_id"],
        FactServiceStats.template_id == dimension_values["template_id"],
        FactServiceStats.notification_type == dimension_values["notification_type"],
        FactServiceStats.notification_status == dimension_values["notification_status"],
    )

    if delta > 0:
        stmt = insert(FactServiceStats).values(
            id=uuid.uuid4(),
            **dimension_values,
            count=delta,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uix_ft_service_stats_dimensions",
            set_={
                "count": FactServiceStats.count + delta,
            },
        )
        db.session.execute(stmt)
    else:
        (
            db.session.query(FactServiceStats)
            .filter(*filters)
            .update(
                {
                    "count": func.greatest(FactServiceStats.count + delta, 0),
                },
                synchronize_session=False,
            )
        )


# 3. Public read API that returns all stats rows for a single service, with a
# defensive guard to avoid querying when no service id is provided.
def dao_fetch_stats_for_service(service_id: UUID) -> list[FactServiceStats]:
    """
    Fetch service stats for a specific service.

    Args:
        service_id: UUID of the service to fetch stats for

    Returns:
        List of FactServiceStats records for the specified service
    """
    if not service_id:
        return []

    return db.session.query(FactServiceStats).filter(FactServiceStats.service_id == service_id).all()
