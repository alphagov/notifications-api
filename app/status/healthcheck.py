from flask import (
    jsonify,
    Blueprint,
    request
)

from app import db, version

status = Blueprint('status', __name__)


@status.route('/', methods=['GET'])
@status.route('/_status', methods=['GET', 'POST'])
def show_status():
    if request.args.get('simple', None):
        return jsonify(status="ok"), 200
    else:
        return jsonify(
            status="ok",  # This should be considered part of the public API
            travis_commit=version.__travis_commit__,
            travis_build_number=version.__travis_job_number__,
            build_time=version.__time__,
            db_version=get_db_version()), 200


def get_db_version():
    query = 'SELECT version_num FROM alembic_version'
    full_name = db.session.execute(query).fetchone()[0]
    return full_name
