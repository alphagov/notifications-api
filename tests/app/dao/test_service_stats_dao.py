from app.dao.service_stats_dao import (
    apply_service_stats_delete,
    apply_service_stats_insert,
    apply_service_stats_update_transition,
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


def test_apply_service_stats_insert_creates_and_increments_row(notify_db_session, sample_service):
    template = create_template(service=sample_service, template_type="email")
    dimensions = _build_dimensions(service_id=sample_service.id, template_id=template.id)

    apply_service_stats_insert(dimensions)
    apply_service_stats_insert(dimensions)
    notify_db_session.commit()

    row = _get_service_stats_row(dimensions)

    assert row is not None
    assert row.count == 2


def test_apply_service_stats_delete_does_not_drop_below_zero(notify_db_session, sample_service):
    template = create_template(service=sample_service, template_type="email")
    dimensions = _build_dimensions(service_id=sample_service.id, template_id=template.id)

    apply_service_stats_insert(dimensions)
    apply_service_stats_delete(dimensions)
    apply_service_stats_delete(dimensions)
    notify_db_session.commit()

    row = _get_service_stats_row(dimensions)

    assert row is not None
    assert row.count == 0


def test_apply_service_stats_update_transition_moves_count_between_statuses(notify_db_session, sample_service):
    template = create_template(service=sample_service, template_type="email")
    old_dimensions = _build_dimensions(
        service_id=sample_service.id,
        template_id=template.id,
        notification_status="sending",
    )
    new_dimensions = _build_dimensions(
        service_id=sample_service.id,
        template_id=template.id,
        notification_status="delivered",
    )

    apply_service_stats_insert(old_dimensions)
    apply_service_stats_update_transition(old_dimensions, new_dimensions)
    notify_db_session.commit()

    old_row = _get_service_stats_row(old_dimensions)
    new_row = _get_service_stats_row(new_dimensions)

    assert old_row is not None
    assert new_row is not None
    assert old_row.count == 0
    assert new_row.count == 1


def test_apply_service_stats_update_transition_noops_when_dimensions_match(notify_db_session, sample_service):
    template = create_template(service=sample_service, template_type="email")
    dimensions = _build_dimensions(service_id=sample_service.id, template_id=template.id)

    apply_service_stats_insert(dimensions)
    apply_service_stats_update_transition(dimensions, dimensions)
    notify_db_session.commit()

    row = _get_service_stats_row(dimensions)

    assert row is not None
    assert row.count == 1
