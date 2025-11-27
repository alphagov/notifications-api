from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import db, version
from app.dao.organisation_dao import dao_count_organisations_with_live_services
from app.dao.services_dao import dao_count_live_services

status = Blueprint("status", __name__)


@status.route("/", methods=["GET"])
@status.route("/_status", methods=["GET", "POST"])
def show_status():
    if request.args.get("simple", None):
        return jsonify(status="ok"), 200
    else:
        return (
            jsonify(
                status="ok",  # This should be considered part of the public API
                git_commit=version.__git_commit__,
                build_time=version.__time__,
                db_version=get_db_version(),
                db_bulk_version=get_db_version(session=db.session_bulk, raise_db_exception=False),
            ),
            200,
        )


@status.route("/_status/live-service-and-organisation-counts")
def live_service_and_organisation_counts():
    return (
        jsonify(
            organisations=dao_count_organisations_with_live_services(),
            services=dao_count_live_services(),
        ),
        200,
    )


def get_db_version(session=db.session, raise_db_exception=True):
    try:
        query = "SELECT version_num FROM alembic_version"
        full_name = session.execute(text(query)).fetchone()[0]
        return full_name
    except DBAPIError as e:
        if raise_db_exception:
            raise

        current_app.logger.exception("Ignoring exception %s", e)
        return None
