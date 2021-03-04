from datetime import datetime

from flask import Blueprint, request, jsonify

from app.dao.fact_notification_status_dao import get_total_notifications_for_date_range
from app.dao.fact_processing_time_dao import get_processing_time_percentage_for_date_range
from app.dao.services_dao import get_live_services_with_organisation
from app.errors import register_errors
from app.performance_platform.performance_platform_schema import performance_platform_request
from app.schema_validation import validate

performance_platform_blueprint = Blueprint('performance_platform', __name__, url_prefix='/performance-platform')

register_errors(performance_platform_blueprint)


@performance_platform_blueprint.route('')
def get_performance_platform():
    # All statistics are as of last night this matches the existing performance platform
    # and avoids the need to query notifications.
    if request.args:
        # Is it ok to reuse this? - should probably create a new one
        validate(request.args, performance_platform_request)

    # If start and end date are not set, we are expecting today's stats.
    today = str(datetime.utcnow().date())

    start_date = datetime.strptime(request.args.get('start_date', today), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.args.get('end_date', today), '%Y-%m-%d').date()
    results = get_total_notifications_for_date_range(start_date=start_date, end_date=end_date)
    total_notifications, emails, sms, letters = transform_results_into_totals(results)
    processing_time_results = get_processing_time_percentage_for_date_range(start_date=start_date, end_date=end_date)
    services = get_live_services_with_organisation()
    stats = {
        "total_notifications": total_notifications,
        "email_notifications": emails,
        "sms_notifications": sms,
        "letter_notifications": letters,
        "notifications_by_type": transform_results_to_json(results),
        "processing_time": transform_processing_time_results_to_json(processing_time_results),
        "live_service_count": len(services),
        "services_using_notify": transform_services_to_json(services)

    }

    return jsonify(stats)


def transform_results_into_totals(results):
    total_notifications = 0
    emails = 0
    sms = 0
    letters = 0
    for x in results:
        total_notifications += x.emails
        total_notifications += x.sms
        total_notifications += x.letters
        emails += x.emails
        sms += x.sms
        letters += x.letters
    return total_notifications, emails, sms, letters


def transform_results_to_json(results):
    j = []
    for x in results:
        j.append({"date": x.bst_date, "emails": x.emails, "sms": x.sms, "letters": x.letters})
    return j


def transform_processing_time_results_to_json(results):
    j = []
    for x in results:
        j.append({"date": x.date, "percentage_under_10_seconds": round(x.percentage, 1)})

    return j


def transform_services_to_json(results):
    j=[]
    for x in results:
        j.append({"service_id": x.service_id, "service_name": x.service_name,
                  "organisation_id": x.organisation_id, "organisation_name": x.organisation_name}
                 )
    return j