from pydoc import text

from flask import Blueprint, jsonify

from app.celery.process_replication_slot_changes import check_replication_slot_changes
from app.v2.errors import register_errors
from tests.app import db

replication_blueprint = Blueprint("replication", __name__, url_prefix="/replication")
register_errors(replication_blueprint)


@replication_blueprint.route("/process-slot-changes", methods=["POST"])
def trigger_process_replication_slot_changes():
    check_replication_slot_changes.apply_async()
    return jsonify({"message": "check-replication-slot-changes task queued"}), 201


@replication_blueprint.route("/check-slot-changes", methods=["GET"])
def trigger_check_replication_slot_changes():
    result = db.session.execute(
        text("""
            SELECT * FROM pg_logical_slot_peek_changes(
                'notify_dashboard_replication_slot',
                NULL,
                NULL,
                'pretty-print', 'on',
                'add-tables', 'public.notifications'
            );
        """)
    )
    changes = result.fetchall()

    return jsonify({"data": changes}), 200
