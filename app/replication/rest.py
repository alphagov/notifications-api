from datetime import datetime
import random
from uuid import UUID, uuid4

from flask import Blueprint, jsonify, request

from app import db
from app.celery.process_replication_slot_changes import check_replication_slot_changes
from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    SMS_TYPE,
)
from app.dao.service_stats_dao import dao_fetch_stats_for_service
from app.models import Notification, Template
from app.replication.replication_changes_utils import get_replication_changes
from app.v2.errors import register_errors

replication_blueprint = Blueprint("replication", __name__, url_prefix="/replication")
register_errors(replication_blueprint)

MAX_NOTIFICATION_COUNT = 50000
MAX_UPDATES_PER_NOTIFICATION = 5
DEFAULT_NOTIFICATION_COUNT = 1000
DEFAULT_UPDATES_PER_NOTIFICATION = 2
DEFAULT_RETURNED_IDS = 20


@replication_blueprint.route("/process-slot-changes", methods=["POST"])
def trigger_process_replication_slot_changes():
    check_replication_slot_changes()
    return jsonify({"message": "check-replication-slot-changes task executed"}), 201


@replication_blueprint.route("/check-slot-changes", methods=["GET"])
def trigger_check_replication_slot_changes():
    changes = get_replication_changes(peek=True)

    return jsonify({"changes": changes}), 200


@replication_blueprint.route("/simulate-notification-load", methods=["POST"])
def simulate_notification_load():
    payload = request.get_json(silent=True) or {}

    notification_count, error = _parse_positive_int(
        payload.get("notification_count", DEFAULT_NOTIFICATION_COUNT),
        "notification_count",
        max_value=MAX_NOTIFICATION_COUNT,
    )
    if error:
        return jsonify({"message": error}), 400

    updates_per_notification, error = _parse_positive_int(
        payload.get("updates_per_notification", DEFAULT_UPDATES_PER_NOTIFICATION),
        "updates_per_notification",
        max_value=MAX_UPDATES_PER_NOTIFICATION,
    )
    if error:
        return jsonify({"message": error}), 400

    template, error = _resolve_template(payload)
    if error:
        return jsonify({"message": error}), 400

    random_seed = payload.get("random_seed")
    randomizer = random.Random(random_seed) if random_seed is not None else random.Random()

    notification_ids, status_breakdown = _insert_and_update_notifications(
        template=template,
        notification_count=notification_count,
        updates_per_notification=updates_per_notification,
        randomizer=randomizer,
    )
    returned_id_count = min(len(notification_ids), DEFAULT_RETURNED_IDS)
    total_updates = notification_count * updates_per_notification

    return (
        jsonify(
            {
                "message": "notification send/update load inserted into notifications table",
                "notification_count": notification_count,
                "updates_per_notification": updates_per_notification,
                "inserted_count": notification_count,
                "updated_count": total_updates,
                "service_id": str(template.service_id),
                "template_id": str(template.id),
                "template_version": template.version,
                "status_breakdown": status_breakdown,
                "inserted_notification_ids": notification_ids[:returned_id_count],
            }
        ),
        200,
    )


@replication_blueprint.route("/stats/<uuid:service_id>", methods=["GET"])
def get_service_stats(service_id):
    """
    Get service stats for a specific service.

    Path parameter:
    - service_id: UUID of the service

    Returns:
    - List of stats entries with:
      - template_id: UUID of the template
      - notification_type: Type of notification (email, sms, letter)
      - notification_status: Status of the notification
      - count: Number of notifications with this status
    """
    stats = dao_fetch_stats_for_service(service_id)

    result = []
    for stat in stats:
        result.append({
            "template_id": str(stat.template_id),
            "notification_type": stat.notification_type,
            "notification_status": stat.notification_status,
            "count": stat.count,
        })

    return jsonify({"stats": result}), 200


def _parse_positive_int(value, field_name, max_value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{field_name} must be an integer"

    if parsed < 1:
        return None, f"{field_name} must be greater than 0"

    if parsed > max_value:
        return None, f"{field_name} must be less than or equal to {max_value}"

    return parsed, None


def _resolve_template(payload):
    template_id = payload.get("template_id")
    service_id = payload.get("service_id")

    query = Template.query
    if template_id:
        try:
            query = query.filter(Template.id == UUID(str(template_id)))
        except (ValueError, TypeError):
            return None, "template_id must be a valid UUID"

    if service_id:
        try:
            query = query.filter(Template.service_id == UUID(str(service_id)))
        except (ValueError, TypeError):
            return None, "service_id must be a valid UUID"

    template = query.order_by(Template.created_at.asc()).first()
    if not template:
        return None, "No template found for the provided service/template filters"

    return template, None


def _insert_and_update_notifications(template, notification_count, updates_per_notification, randomizer):
    inserted_notifications = []
    status_breakdown = {}
    now = datetime.utcnow()

    for index in range(notification_count):
        terminal_status = _pick_terminal_status(template.template_type, randomizer)
        status_path = _build_status_path(terminal_status, updates_per_notification)

        notification = Notification(
            id=uuid4(),
            to=_build_recipient(template.template_type, index),
            service_id=template.service_id,
            template_id=template.id,
            template_version=template.version,
            key_type=KEY_TYPE_NORMAL,
            notification_type=template.template_type,
            created_at=now,
            status=NOTIFICATION_SENDING,
            billable_units=1,
            postage="second" if template.template_type == LETTER_TYPE else None,
            rate_multiplier=1 if template.template_type == SMS_TYPE else None,
        )
        db.session.add(notification)
        inserted_notifications.append((notification, status_path))

    db.session.flush()

    for notification, status_path in inserted_notifications:
        for status in status_path:
            notification.status = status
            notification.updated_at = datetime.utcnow()
            if status in {NOTIFICATION_SENT, NOTIFICATION_DELIVERED}:
                notification.sent_at = datetime.utcnow()

        status_breakdown[notification.status] = status_breakdown.get(notification.status, 0) + 1

    db.session.commit()

    return [str(notification.id) for notification, _ in inserted_notifications], status_breakdown


def _pick_terminal_status(template_type, randomizer):
    if template_type == LETTER_TYPE:
        statuses = [NOTIFICATION_DELIVERED, NOTIFICATION_SENT]
        weights = [85, 15]
    else:
        statuses = [NOTIFICATION_DELIVERED, NOTIFICATION_SENT]
        weights = [80, 20]

    return randomizer.choices(statuses, weights=weights, k=1)[0]


def _build_status_path(terminal_status, updates_per_notification):
    if updates_per_notification <= 0:
        return []

    if updates_per_notification == 1:
        return [terminal_status]

    if terminal_status == NOTIFICATION_DELIVERED:
        base_path = [NOTIFICATION_SENT, NOTIFICATION_DELIVERED]
    elif terminal_status == NOTIFICATION_SENT:
        base_path = [NOTIFICATION_SENT]
    else:
        base_path = [NOTIFICATION_SENT, terminal_status]

    if len(base_path) >= updates_per_notification:
        return base_path[:updates_per_notification]

    return base_path + [base_path[-1]] * (updates_per_notification - len(base_path))


def _build_recipient(template_type, index):
    if template_type == SMS_TYPE:
        return f"+447700900{index % 1000:03d}"
    if template_type == EMAIL_TYPE:
        return f"load-test-{index}@example.com"
    if template_type == LETTER_TYPE:
        return "Load Test User\n1 Test Street\nTest City\nSW1A 1AA"
    return f"load-test-{index}@example.com"

