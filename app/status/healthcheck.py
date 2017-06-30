from datetime import (
    datetime,
    timedelta
)

from flask import (
    jsonify,
    Blueprint,
    request,
    current_app
)

from app import db, version
from app.models import Notification

status = Blueprint('status', __name__)


@status.route('/_status', methods=['GET', 'POST'])
def show_status():
    if request.args.get('elb', None):
        return jsonify(status="ok"), 200
    else:
        return jsonify(
            status="ok",
            travis_commit=version.__travis_commit__,
            travis_build_number=version.__travis_job_number__,
            build_time=version.__time__,
            db_version=get_db_version()), 200


@status.route('/_delivery_status')
def show_delivery_status():
    if request.args.get('elb', None):
        return jsonify(status="ok"), 200
    else:
        notifications_alert = current_app.config['NOTIFICATIONS_ALERT']
        some_number_of_minutes_ago = datetime.utcnow() - timedelta(minutes=notifications_alert)
        notifications = Notification.query.filter(Notification.status == 'sending',
                                                  Notification.created_at < some_number_of_minutes_ago).all()
        message = "{} notifications in sending state over {} minutes".format(len(notifications), notifications_alert)
        if notifications:
            return jsonify(
                status="error",
                message=message,
                travis_commit=version.__travis_commit__,
                travis_build_number=version.__travis_job_number__,
                build_time=version.__time__,
                db_version=get_db_version()), 500

        return jsonify(
            status="ok",
            message=message,
            travis_commit=version.__travis_commit__,
            travis_build_number=version.__travis_job_number__,
            build_time=version.__time__,
            db_version=get_db_version()), 200


def get_db_version():
    try:
        query = 'SELECT version_num FROM alembic_version'
        full_name = db.session.execute(query).fetchone()[0]
        return full_name
    except:
        return 'n/a'
