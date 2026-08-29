from datetime import date
from typing import TypedDict
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app import db
from app.models import FactServiceStats


class ServiceStatsDimensions(TypedDict):
    bst_date: date
    service_id: UUID
    template_id: UUID
    notification_type: str
    notification_status: str


# 1. Public write API used by callers to apply a single aggregated count change into
# service statistics for a specific dimensions tuple.
def apply_service_stats_change(dimensions: ServiceStatsDimensions, change_count: int) -> None:
    _update_service_stats_count(dimensions, change_count)


# 2. Internal persistence routine that applies the count change with UPSERT behavior for
# positive changes and bounded decrement behavior for negative changes.
def _update_service_stats_count(dimensions: ServiceStatsDimensions, change_count: int) -> None:
    if change_count == 0:
        return

    dimension_values = {
        "bst_date": dimensions["bst_date"],
        "service_id": dimensions["service_id"],
        "template_id": dimensions["template_id"],
        "notification_type": dimensions["notification_type"],
        "notification_status": dimensions["notification_status"],
    }
    filters = (
        FactServiceStats.bst_date == dimension_values["bst_date"],
        FactServiceStats.service_id == dimension_values["service_id"],
        FactServiceStats.template_id == dimension_values["template_id"],
        FactServiceStats.notification_type == dimension_values["notification_type"],
        FactServiceStats.notification_status == dimension_values["notification_status"],
    )

    if change_count > 0:
        stmt = insert(FactServiceStats).values(
            **dimension_values,
            notification_count=change_count,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="ft_service_stats_pkey",
            set_={
                "notification_count": FactServiceStats.notification_count + change_count,
            },
        )
        db.session.execute(stmt)
    else:
        (
            db.session.query(FactServiceStats)
            .filter(*filters)
            .update(
                {
                    "notification_count": func.greatest(FactServiceStats.notification_count + change_count, 0),
                },
                synchronize_session=False,
            )
        )
