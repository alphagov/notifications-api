from flask import (
    jsonify,
    Blueprint,
    request
)

from app import db, version
from app.dao.services_dao import dao_count_live_services
from app.dao.organisation_dao import dao_count_organisations_with_live_services
from app.tracing import trace_request

status = Blueprint('status', __name__)


@status.route('/', methods=['GET'])
@status.route('/_status', methods=['GET', 'POST'])
@trace_request
def show_status():
    if request.args.get('simple', None):
        return jsonify(status="ok"), 200
    else:
        return jsonify(
            status="ok",  # This should be considered part of the public API
            git_commit=version.__git_commit__,
            build_time=version.__time__,
            db_version=get_db_version()), 200


@status.route('/_status/live-service-and-organisation-counts')
def live_service_and_organisation_counts():
    return jsonify(
        organisations=dao_count_organisations_with_live_services(),
        services=dao_count_live_services(),
    ), 200


def get_db_version():
    query = 'SELECT version_num FROM alembic_version'
    full_name = db.session.execute(query).fetchone()[0]
    return full_name
