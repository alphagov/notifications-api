from flask import jsonify

from flask import Blueprint
status = Blueprint('status', __name__)


@status.route('/_status', methods=['GET', 'POST'])
def show_status():
    from app import (get_api_version, get_db_version)
    return jsonify(status="ok",
                   api_version=get_api_version(),
                   db_version=get_db_version()), 200
