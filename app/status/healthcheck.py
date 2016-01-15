from flask import jsonify

from flask import Blueprint
status = Blueprint('status', __name__)


@status.route('/_status', methods=['GET', 'POST'])
def show_status():
    return jsonify(
        status="ok",
    ), 200
