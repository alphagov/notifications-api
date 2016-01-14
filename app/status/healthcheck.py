from flask import jsonify

from flask import Blueprint
status = Blueprint('status', __name__)


@status.route('/_status')
def show_status():
    return jsonify(
        status="ok",
    ), 200
