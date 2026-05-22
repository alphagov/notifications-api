from app.dao.service_stats_dao import (
    apply_service_stats_delta,
)
from app.models import ServiceStats
from tests.app.db import create_template


def _build_dimensions(*, service_id, template_id, notification_type="email", notification_status="created"):
    return {
        "service_id": service_id,
        "template_id": template_id,
        "notification_type": notification_type,
        "notification_status": notification_status,
    }


def _get_service_stats_row(dimensions):
    return ServiceStats.query.filter_by(
        service_id=dimensions["service_id"],
        template_id=dimensions["template_id"],
        notification_type=dimensions["notification_type"],
        notification_status=dimensions["notification_status"],
    ).first()


def test_apply_service_stats_delta_supports_positive_and_negative_values(notify_db_session, sample_service):
    template = create_template(service=sample_service, template_type="email")
    dimensions = _build_dimensions(service_id=sample_service.id, template_id=template.id)

    apply_service_stats_delta(dimensions, 5)
    apply_service_stats_delta(dimensions, -3)
    apply_service_stats_delta(dimensions, -10)
    notify_db_session.commit()

    row = _get_service_stats_row(dimensions)

    assert row is not None
    assert row.count == 0
