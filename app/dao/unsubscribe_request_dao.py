from datetime import datetime

from sqlalchemy import desc, func

from app import db
from app.dao.dao_utils import autocommit
from app.models import (
    Job,
    Notification,
    NotificationHistory,
    Template,
    UnsubscribeRequest,
    UnsubscribeRequestHistory,
    UnsubscribeRequestReport,
)
from app.utils import midnight_n_days_ago


@autocommit
def create_unsubscribe_request_dao(unsubscribe_data):
    db.session.add(UnsubscribeRequest(**unsubscribe_data))


def get_unsubscribe_request_by_notification_id_dao(notification_id):
    return UnsubscribeRequest.query.filter_by(notification_id=notification_id).one()


def get_unsubscribe_requests_statistics_dao(service_id):
    """
    This method returns statistics for only unsubscribe requests received
    in the last 7 days
    """
    return (
        db.session.query(
            func.count(UnsubscribeRequest.service_id).label("unsubscribe_requests_count"),
            UnsubscribeRequest.service_id.label("service_id"),
            func.max(UnsubscribeRequest.created_at).label("datetime_of_latest_unsubscribe_request"),
        )
        .select_from(UnsubscribeRequest)
        .filter(
            UnsubscribeRequest.service_id == service_id,
            UnsubscribeRequest.created_at >= midnight_n_days_ago(7),
        )
        .group_by(UnsubscribeRequest.service_id)
        .one_or_none()
    )


def get_latest_unsubscribe_request_date_dao(service_id):
    return (
        db.session.query(
            UnsubscribeRequest.created_at.label("datetime_of_latest_unsubscribe_request"),
        )
        .filter(
            UnsubscribeRequest.service_id == service_id,
        )
        .order_by(desc(UnsubscribeRequest.created_at))
        .first()
    )


def get_unsubscribe_request_reports_dao(service_id):
    return (
        UnsubscribeRequestReport.query.filter(UnsubscribeRequestReport.service_id == service_id)
        .join(UnsubscribeRequest, UnsubscribeRequest.unsubscribe_request_report_id == UnsubscribeRequestReport.id)
        .order_by(desc(UnsubscribeRequestReport.latest_timestamp))
        .distinct()
    )


def get_unsubscribe_request_report_by_id_dao(batch_id):
    return UnsubscribeRequestReport.query.filter_by(id=batch_id).one_or_none()


def get_unsubscribe_requests_data_for_download_dao(service_id, batch_id):
    results = []
    for table in [Notification, NotificationHistory]:
        query = (
            db.session.query(
                UnsubscribeRequest.notification_id,
                UnsubscribeRequest.email_address,
                Template.name.label("template_name"),
                table.template_id,
                func.coalesce(Job.original_file_name, "N/A").label("original_file_name"),
                table.sent_at.label("template_sent_at"),
                UnsubscribeRequest.created_at.label("unsubscribe_request_received_at"),
            )
            .outerjoin(Job, table.job_id == Job.id)
            .filter(
                UnsubscribeRequest.service_id == service_id,
                UnsubscribeRequest.unsubscribe_request_report_id == batch_id,
                UnsubscribeRequest.notification_id == table.id,
                table.template_id == Template.id,
            )
            .order_by(desc(Template.name), desc(Job.original_file_name), desc(table.sent_at))
        )
        results = results + query.all()
    return results


def get_unbatched_unsubscribe_requests_dao(service_id):
    return (
        UnsubscribeRequest.query.filter_by(service_id=service_id, unsubscribe_request_report_id=None)
        .order_by(UnsubscribeRequest.created_at.desc())
        .all()
    )


@autocommit
def create_unsubscribe_request_reports_dao(unsubscribe_request_report):
    db.session.add(unsubscribe_request_report)


@autocommit
def update_unsubscribe_request_report_processed_by_date_dao(report, report_has_been_processed):
    report.processed_by_service_at = datetime.utcnow() if report_has_been_processed else None
    db.session.add(report)


@autocommit
def assign_unbatched_unsubscribe_requests_to_report_dao(report_id, service_id, earliest_timestamp, latest_timestamp):
    """
    This method updates the unsubscribe_request_report_id of all un-batched unsubscribe requests that fall
    within the earliest_timestamp and latest_timestamp values to report_id
    """
    UnsubscribeRequest.query.filter(
        UnsubscribeRequest.unsubscribe_request_report_id.is_(None),
        UnsubscribeRequest.service_id == service_id,
        UnsubscribeRequest.created_at >= earliest_timestamp,
        UnsubscribeRequest.created_at <= latest_timestamp,
    ).update({"unsubscribe_request_report_id": report_id})


def get_service_ids_with_unsubscribe_requests():
    return {row.service_id for row in UnsubscribeRequest.query.distinct()}


def dao_archive_batched_unsubscribe_requests(service_id):
    return archive_unsubscribe_requests_from_query(
        UnsubscribeRequest.query.join(
            UnsubscribeRequestReport,
            UnsubscribeRequest.unsubscribe_request_report_id == UnsubscribeRequestReport.id,
        ).filter(
            UnsubscribeRequestReport.created_at < midnight_n_days_ago(7),
            UnsubscribeRequest.service_id == service_id,
        )
    )


def dao_archive_old_unsubscribe_requests(service_id):
    return archive_unsubscribe_requests_from_query(
        UnsubscribeRequest.query.filter(
            UnsubscribeRequest.created_at < midnight_n_days_ago(90),
            UnsubscribeRequest.service_id == service_id,
            UnsubscribeRequest.unsubscribe_request_report_id.is_(None),
        )
    )


def archive_unsubscribe_requests_from_query(query):
    rows = [unsubscribe_request.serialize_for_history() for unsubscribe_request in query.all()]

    if not rows:
        return 0

    db.session.execute(UnsubscribeRequestHistory.__table__.insert().values(rows))
    delete_result = db.session.execute(
        UnsubscribeRequest.__table__.delete().where(UnsubscribeRequest.id.in_({row["id"] for row in rows}))
    )

    return delete_result.rowcount
