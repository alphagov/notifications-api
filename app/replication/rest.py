from flask import Blueprint, jsonify

from app.celery.process_replication_slot_changes import check_replication_slot_changes
from app.dao.fact_service_stats_dao import dao_fetch_stats_for_service
from app.replication.performance_test import simulate_notification_load as performance_test_simulate_notification_load
from app.replication.replication_changes_utils import get_replication_changes
from app.v2.errors import register_errors

replication_blueprint = Blueprint("replication", __name__, url_prefix="/replication")
register_errors(replication_blueprint)


@replication_blueprint.route("/process-slot-changes", methods=["POST"])
# Trigger immediate processing of pending replication slot changes via the Celery task.
# This endpoint is mainly operational, allowing manual execution for verification
# or recovery scenarios when scheduled processing needs to be nudged.
def trigger_process_replication_slot_changes():
    check_replication_slot_changes()
    return jsonify({"message": "check-replication-slot-changes task executed"}), 201


@replication_blueprint.route("/check-slot-changes", methods=["GET"])
# Inspect replication slot changes in peek mode so callers can review pending records
# without consuming or advancing the slot position. Useful for debugging parser logic
# and validating what data would be processed by the worker task.
def trigger_check_replication_slot_changes():
    changes = get_replication_changes(peek=True)

    return jsonify({"changes": changes}), 200


@replication_blueprint.route("/simulate-notification-load", methods=["POST"])
# Run a controlled notification-load simulation used for replication performance testing.
# The underlying helper encapsulates test data generation and returns a response payload
# describing the simulated operation outcome.
def simulate_notification_load():
    return performance_test_simulate_notification_load()


@replication_blueprint.route("/stats/<uuid:service_id>", methods=["GET"])
# Return aggregated service statistics grouped by template, notification type, and
# notification status for the requested service id, formatted for API consumers.
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



