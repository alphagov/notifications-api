from flask import Blueprint, jsonify

from app.celery.process_replication_slot_changes import check_replication_slot_changes
from app.v2.errors import register_errors

replication_blueprint = Blueprint("replication", __name__, url_prefix="/replication")
register_errors(replication_blueprint)


@replication_blueprint.route("/process-slot-changes", methods=["POST"])
def trigger_process_replication_slot_changes():
    check_replication_slot_changes.apply_async()
    return jsonify({"message": "check-replication-slot-changes task queued"}), 201
