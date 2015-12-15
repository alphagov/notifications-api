from flask import jsonify

from app.status import status


@status.route('/_status')
def status():
    return jsonify(
        status="ok",
    ), 200
