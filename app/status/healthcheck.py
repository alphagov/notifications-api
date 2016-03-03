from flask import jsonify

from flask import Blueprint, request

from app import db, version

status = Blueprint('status', __name__)


@status.route('/_status', methods=['GET', 'POST'])
def show_status():
    travis_commit, travis_build_number, build_time = get_api_version()
    if request.args.get('elb', None):
        return jsonify(status="ok"), 200
    else:
        return jsonify(
            status="ok",
            travis_commit=travis_commit,
            travis_build_number=travis_build_number,
            build_time=build_time,
            db_version=get_db_version()), 200


def get_api_version():
    travis_commit = 'n/a'
    travis_job_number = 'n/a'
    build_time = "n/a"
    try:
        travis_commit = version.__travis_commit__
        travis_job_number = version.__travis_job_number__
        build_time = version.__time__
    except:
        pass
    return travis_commit, travis_job_number, build_time


def get_db_version():
    try:
        query = 'SELECT version_num FROM alembic_version'
        full_name = db.session.execute(query).fetchone()[0]
        return full_name
    except:
        return 'n/a'
