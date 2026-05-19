from flask import Blueprint, jsonify

from app.celery.process_replication_slot_changes import check_replication_slot_changes
from app.replication.replication_changes_utils import get_replication_changes
from app.v2.errors import register_errors

replication_blueprint = Blueprint("replication", __name__, url_prefix="/replication")
register_errors(replication_blueprint)


@replication_blueprint.route("/process-slot-changes", methods=["POST"])
def trigger_process_replication_slot_changes():
    check_replication_slot_changes()
    return jsonify({"message": "check-replication-slot-changes task executed"}), 201


@replication_blueprint.route("/check-slot-changes", methods=["GET"])
def trigger_check_replication_slot_changes():
    changes = get_replication_changes(peek=True)

    return jsonify({"changes": changes}), 200
