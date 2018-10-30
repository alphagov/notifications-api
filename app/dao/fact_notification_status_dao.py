from datetime import datetime, timedelta, time

from flask import current_app
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.expression import literal
from sqlalchemy.types import DateTime

from app import db
from app.models import Notification, NotificationHistory, FactNotificationStatus, KEY_TYPE_TEST
from app.utils import convert_bst_to_utc, get_london_midnight_in_utc, midnight_n_days_ago


def fetch_notification_status_for_day(process_day, service_id=None):
    start_date = convert_bst_to_utc(datetime.combine(process_day, time.min))
    end_date = convert_bst_to_utc(datetime.combine(process_day + timedelta(days=1), time.min))
    # use notification_history if process day is older than 7 days
    # this is useful if we need to rebuild the ft_billing table for a date older than 7 days ago.
    current_app.logger.info("Fetch ft_notification_status for {} to {}".format(start_date, end_date))
    table = Notification
    if start_date < datetime.utcnow() - timedelta(days=7):
        table = NotificationHistory

    transit_data = db.session.query(
        table.template_id,
        table.service_id,
        func.coalesce(table.job_id, '00000000-0000-0000-0000-000000000000').label('job_id'),
        table.notification_type,
        table.key_type,
        table.status,
        func.count().label('notification_count')
    ).filter(
        table.created_at >= start_date,
        table.created_at < end_date
    ).group_by(
        table.template_id,
        table.service_id,
        'job_id',
        table.notification_type,
        table.key_type,
        table.status
    )

    if service_id:
        transit_data = transit_data.filter(table.service_id == service_id)

    return transit_data.all()


def update_fact_notification_status(data, process_day):
    table = FactNotificationStatus.__table__
    '''
       This uses the Postgres upsert to avoid race conditions when two threads try to insert
       at the same row. The excluded object refers to values that we tried to insert but were
       rejected.
       http://docs.sqlalchemy.org/en/latest/dialects/postgresql.html#insert-on-conflict-upsert
    '''
    for row in data:
        stmt = insert(table).values(
            bst_date=process_day.date(),
            template_id=row.template_id,
            service_id=row.service_id,
            job_id=row.job_id,
            notification_type=row.notification_type,
            key_type=row.key_type,
            notification_status=row.status,
            notification_count=row.notification_count,
        )

        stmt = stmt.on_conflict_do_update(
            constraint="ft_notification_status_pkey",
            set_={"notification_count": stmt.excluded.notification_count,
                  "updated_at": datetime.utcnow()
                  }
        )
        db.session.connection().execute(stmt)
        db.session.commit()


def fetch_notification_status_for_service_by_month(start_date, end_date, service_id):
    return db.session.query(
        func.date_trunc('month', FactNotificationStatus.bst_date).label('month'),
        FactNotificationStatus.notification_type,
        FactNotificationStatus.notification_status,
        func.sum(FactNotificationStatus.notification_count).label('count')
    ).filter(
        FactNotificationStatus.service_id == service_id,
        FactNotificationStatus.bst_date >= start_date,
        FactNotificationStatus.bst_date < end_date,
        FactNotificationStatus.key_type != KEY_TYPE_TEST
    ).group_by(
        func.date_trunc('month', FactNotificationStatus.bst_date).label('month'),
        FactNotificationStatus.notification_type,
        FactNotificationStatus.notification_status
    ).all()


def fetch_notification_status_for_service_for_7_days(service_id):
    start_date = midnight_n_days_ago(7)
    return db.session.query(
        FactNotificationStatus.bst_date,
        FactNotificationStatus.notification_type,
        FactNotificationStatus.notification_status,
        func.sum(FactNotificationStatus.notification_count).label('count')
    ).filter(
        FactNotificationStatus.service_id == service_id,
        FactNotificationStatus.bst_date >= start_date,
        FactNotificationStatus.key_type != KEY_TYPE_TEST
    ).group_by(
        FactNotificationStatus.bst_date,
        FactNotificationStatus.notification_type,
        FactNotificationStatus.notification_status,
    ).all()


def fetch_notification_status_for_service_for_day(bst_day, service_id):
    return db.session.query(
        # return current month as a datetime so the data has the same shape as the ft_notification_status query
        literal(bst_day.replace(day=1), type_=DateTime).label('month'),
        Notification.notification_type,
        Notification.status.label('notification_status'),
        func.count().label('count')
    ).filter(
        Notification.created_at >= get_london_midnight_in_utc(bst_day),
        Notification.created_at < get_london_midnight_in_utc(bst_day + timedelta(days=1)),
        Notification.service_id == service_id,
        Notification.key_type != KEY_TYPE_TEST
    ).group_by(
        Notification.notification_type,
        Notification.status
    ).all()
