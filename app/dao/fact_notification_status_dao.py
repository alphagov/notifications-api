from collections.abc import Sequence
from datetime import date, datetime, timedelta
from itertools import chain, groupby
from typing import Any, NamedTuple
from uuid import UUID

from sqlalchemy import Date, Row, case, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, scoped_session
from sqlalchemy.sql.expression import extract, literal
from sqlalchemy.types import DateTime, Integer

from app import db
from app.constants import (
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    NOTIFICATION_CANCELLED,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_PENDING,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
)
from app.dao.dao_utils import autocommit
from app.models import (
    FactNotificationStatus,
    Notification,
    NotificationAllTimeView,
    Service,
    Template,
)
from app.utils import (
    get_london_midnight_in_utc,
    get_london_month_from_utc_column,
    midnight_n_days_ago,
    retryable_query,
)


@retryable_query()
def _generate_fact_notification_status_rows_inner(
    process_day: date,
    notification_type: str,
    service_id: UUID | str,
    chunk_timedelta: timedelta,
    chunk_start_dt: datetime,
    end_dt: datetime,
    session: Session | scoped_session = db.session,
) -> Sequence[Row]:
    return (
        session.query(
            literal(process_day).label("bst_date"),
            NotificationAllTimeView.template_id,
            literal(service_id).label("service_id"),
            func.coalesce(NotificationAllTimeView.job_id, "00000000-0000-0000-0000-000000000000").label("job_id"),
            literal(notification_type).label("notification_type"),
            NotificationAllTimeView.key_type,
            NotificationAllTimeView.status.label("notification_status"),
            func.count().label("notification_count"),
        )
        .filter(
            NotificationAllTimeView.created_at >= chunk_start_dt,
            NotificationAllTimeView.created_at < min(chunk_start_dt + chunk_timedelta, end_dt),
            NotificationAllTimeView.notification_type == notification_type,
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.key_type.in_((KEY_TYPE_NORMAL, KEY_TYPE_TEAM)),
        )
        .group_by(
            NotificationAllTimeView.template_id,
            "job_id",
            NotificationAllTimeView.key_type,
            NotificationAllTimeView.status,
        )
        .all()
    )


def generate_fact_notification_status_rows(
    process_day: date,
    notification_type: str,
    service_id: UUID | str,
    chunk_timedelta: timedelta = timedelta(minutes=15),
    session: Session | scoped_session = db.session,
    inner_retry_attempts: int = 0,
) -> Sequence[NamedTuple]:
    start_dt = get_london_midnight_in_utc(process_day)
    end_dt = get_london_midnight_in_utc(process_day + timedelta(days=1))
    status_data = []  # type: ignore

    # sqlalchemy's public api doesn't give us a way of constructing a new instance of a Row type, so
    # to do in-python aggregation, we need our own NamedTuple based of the fields of the Rows. but we
    # can't set it up until we have the first Row
    nt_type = None

    chunk_start_dt = start_dt
    while chunk_start_dt < end_dt:
        partial_status_data = _generate_fact_notification_status_rows_inner(
            process_day,
            notification_type,
            service_id,
            chunk_timedelta,
            chunk_start_dt,
            end_dt,
            session=session,
            retry_attempts=inner_retry_attempts,  # type: ignore
        )
        if partial_status_data:
            if nt_type is None:
                nt_type = NamedTuple("StatusRow", ((f, Any) for f in partial_status_data[0]._fields))  # type: ignore

            # fold into running aggregation
            status_data = [
                nt_type(  # type: ignore
                    *k,  # grp's common fields
                    *(sum(v) for v in zip(*(r[-1:] for r in grp), strict=True)),
                )
                for k, grp in groupby(sorted(chain(status_data, partial_status_data)), key=lambda r: r[:-1])
            ]

        chunk_start_dt += chunk_timedelta

    return status_data


@autocommit
def update_fact_notification_status(
    rows: Sequence[NamedTuple], process_day: date, notification_type: str, service_id: UUID | str
) -> int:
    if rows and {row.bst_date for row in rows} != {process_day}:  # type: ignore
        raise ValueError("Not all rows bst_date match process_day")

    # delete any existing rows in case some no longer exist in `rows` e.g. if all messages are sent
    # (an upsert alone would not be sufficient here)
    deleted_row_count = db.session.execute(
        delete(FactNotificationStatus)
        .where(
            FactNotificationStatus.bst_date == process_day,
            FactNotificationStatus.notification_type == notification_type,
            FactNotificationStatus.service_id == service_id,
        )
        .execution_options(synchronize_session=False)
    ).rowcount

    db.session.execute(
        insert(FactNotificationStatus)
        .on_conflict_do_nothing(constraint="ft_notification_status_pkey")
        .execution_options(synchronize_session=False),
        (row._asdict() for row in rows),  # type: ignore
    )

    return deleted_row_count


def fetch_notification_status_for_service_by_month(start_date, end_date, service_id):
    return (
        db.session.query(
            func.date_trunc("month", FactNotificationStatus.bst_date).label("month"),
            FactNotificationStatus.notification_type,
            FactNotificationStatus.notification_status,
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .filter(
            FactNotificationStatus.service_id == service_id,
            FactNotificationStatus.bst_date >= start_date,
            FactNotificationStatus.bst_date < end_date,
            FactNotificationStatus.key_type != KEY_TYPE_TEST,
        )
        .group_by(
            func.date_trunc("month", FactNotificationStatus.bst_date).label("month"),
            FactNotificationStatus.notification_type,
            FactNotificationStatus.notification_status,
        )
        .all()
    )


def fetch_notification_status_for_service_for_day(bst_day, service_id):
    return (
        db.session.query(
            # return current month as a datetime so the data has the same shape as the ft_notification_status query
            literal(bst_day.replace(day=1), type_=DateTime).label("month"),
            Notification.notification_type,
            Notification.status.label("notification_status"),
            func.count().label("count"),
        )
        .filter(
            Notification.created_at >= get_london_midnight_in_utc(bst_day),
            Notification.created_at < get_london_midnight_in_utc(bst_day + timedelta(days=1)),
            Notification.service_id == service_id,
            Notification.key_type != KEY_TYPE_TEST,
        )
        .group_by(Notification.notification_type, Notification.status)
        .all()
    )


def fetch_notification_status_for_service_for_today_and_7_previous_days(service_id, by_template=False, limit_days=7):
    start_date = midnight_n_days_ago(limit_days)
    now = datetime.utcnow()
    stats_for_7_days = db.session.query(
        FactNotificationStatus.notification_type.label("notification_type"),
        FactNotificationStatus.notification_status.label("status"),
        *([FactNotificationStatus.template_id.label("template_id")] if by_template else []),
        FactNotificationStatus.notification_count.label("count"),
    ).filter(
        FactNotificationStatus.service_id == service_id,
        FactNotificationStatus.bst_date >= start_date,
        FactNotificationStatus.key_type != KEY_TYPE_TEST,
    )

    stats_for_today = (
        db.session.query(
            Notification.notification_type.cast(db.Text),
            Notification.status,
            *([Notification.template_id] if by_template else []),
            func.count().label("count"),
        )
        .filter(
            Notification.created_at >= get_london_midnight_in_utc(now),
            Notification.service_id == service_id,
            Notification.key_type != KEY_TYPE_TEST,
        )
        .group_by(
            Notification.notification_type, *([Notification.template_id] if by_template else []), Notification.status
        )
    )

    all_stats_table = stats_for_7_days.union_all(stats_for_today).subquery()

    aggregation = (
        db.session.query(
            *([all_stats_table.c.template_id] if by_template else []),
            all_stats_table.c.notification_type,
            all_stats_table.c.status,
            func.cast(func.sum(all_stats_table.c.count), Integer).label("count"),
        )
        .group_by(
            *([all_stats_table.c.template_id] if by_template else []),
            all_stats_table.c.notification_type,
            all_stats_table.c.status,
        )
        .subquery()
    )

    query = db.session.query(
        *(
            [Template.name.label("template_name"), Template.is_precompiled_letter, aggregation.c.template_id]
            if by_template
            else []
        ),
        aggregation.c.notification_type,
        aggregation.c.status,
        aggregation.c.count,
    )

    if by_template:
        query = query.filter(aggregation.c.template_id == Template.id)

    return query.all()


def fetch_notification_status_totals_for_all_services(start_date, end_date):
    stats = (
        db.session.query(
            FactNotificationStatus.notification_type.label("notification_type"),
            FactNotificationStatus.notification_status.label("status"),
            FactNotificationStatus.key_type.label("key_type"),
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .filter(FactNotificationStatus.bst_date >= start_date, FactNotificationStatus.bst_date <= end_date)
        .group_by(
            FactNotificationStatus.notification_type,
            FactNotificationStatus.notification_status,
            FactNotificationStatus.key_type,
        )
    )
    today = get_london_midnight_in_utc(datetime.utcnow())
    if start_date <= datetime.utcnow().date() <= end_date:
        stats_for_today = (
            db.session.query(
                Notification.notification_type.cast(db.Text).label("notification_type"),
                Notification.status,
                Notification.key_type,
                func.count().label("count"),
            )
            .filter(Notification.created_at >= today)
            .group_by(
                Notification.notification_type.cast(db.Text),
                Notification.status,
                Notification.key_type,
            )
        )
        all_stats_table = stats.union_all(stats_for_today).subquery()
        query = (
            db.session.query(
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
                all_stats_table.c.key_type,
                func.cast(func.sum(all_stats_table.c.count), Integer).label("count"),
            )
            .group_by(
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
                all_stats_table.c.key_type,
            )
            .order_by(all_stats_table.c.notification_type)
        )
    else:
        query = stats.order_by(FactNotificationStatus.notification_type)
    return query.all()


def fetch_notification_statuses_for_job(job_id):
    return (
        db.session.query(
            FactNotificationStatus.notification_status.label("status"),
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .filter(
            FactNotificationStatus.job_id == job_id,
        )
        .group_by(FactNotificationStatus.notification_status)
        .all()
    )


def fetch_stats_for_all_services_by_date_range(start_date, end_date, include_from_test_key=True):
    stats = (
        db.session.query(
            FactNotificationStatus.service_id.label("service_id"),
            Service.name.label("name"),
            Service.restricted.label("restricted"),
            Service.active.label("active"),
            Service.created_at.label("created_at"),
            FactNotificationStatus.notification_type.label("notification_type"),
            FactNotificationStatus.notification_status.label("status"),
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .filter(
            FactNotificationStatus.bst_date >= start_date,
            FactNotificationStatus.bst_date <= end_date,
            FactNotificationStatus.service_id == Service.id,
        )
        .group_by(
            FactNotificationStatus.service_id.label("service_id"),
            Service.name,
            Service.restricted,
            Service.active,
            Service.created_at,
            FactNotificationStatus.notification_type,
            FactNotificationStatus.notification_status,
        )
        .order_by(FactNotificationStatus.service_id, FactNotificationStatus.notification_type)
    )
    if not include_from_test_key:
        stats = stats.filter(FactNotificationStatus.key_type != KEY_TYPE_TEST)

    if start_date <= datetime.utcnow().date() <= end_date:
        today = get_london_midnight_in_utc(datetime.utcnow())
        subquery = (
            db.session.query(
                Notification.notification_type.cast(db.Text).label("notification_type"),
                Notification.status.label("status"),
                Notification.service_id.label("service_id"),
                func.count(Notification.id).label("count"),
            )
            .filter(Notification.created_at >= today)
            .group_by(Notification.notification_type, Notification.status, Notification.service_id)
        )
        if not include_from_test_key:
            subquery = subquery.filter(Notification.key_type != KEY_TYPE_TEST)
        subquery = subquery.subquery()

        stats_for_today = db.session.query(
            Service.id.label("service_id"),
            Service.name.label("name"),
            Service.restricted.label("restricted"),
            Service.active.label("active"),
            Service.created_at.label("created_at"),
            subquery.c.notification_type.label("notification_type"),
            subquery.c.status.label("status"),
            subquery.c.count.label("count"),
        ).outerjoin(subquery, subquery.c.service_id == Service.id)

        all_stats_table = stats.union_all(stats_for_today).subquery()
        query = (
            db.session.query(
                all_stats_table.c.service_id,
                all_stats_table.c.name,
                all_stats_table.c.restricted,
                all_stats_table.c.active,
                all_stats_table.c.created_at,
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
                func.cast(func.sum(all_stats_table.c.count), Integer).label("count"),
            )
            .group_by(
                all_stats_table.c.service_id,
                all_stats_table.c.name,
                all_stats_table.c.restricted,
                all_stats_table.c.active,
                all_stats_table.c.created_at,
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
            )
            .order_by(all_stats_table.c.name, all_stats_table.c.notification_type, all_stats_table.c.status)
        )
    else:
        query = stats
    return query.all()


def fetch_monthly_template_usage_for_service(start_date, end_date, service_id):
    # services_dao.replaces dao_fetch_monthly_historical_usage_by_template_for_service
    stats = (
        db.session.query(
            FactNotificationStatus.template_id.label("template_id"),
            Template.name.label("name"),
            Template.template_type.label("template_type"),
            Template.is_precompiled_letter.label("is_precompiled_letter"),
            extract("month", FactNotificationStatus.bst_date).label("month"),
            extract("year", FactNotificationStatus.bst_date).label("year"),
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .join(Template, FactNotificationStatus.template_id == Template.id)
        .filter(
            FactNotificationStatus.service_id == service_id,
            FactNotificationStatus.bst_date >= start_date,
            FactNotificationStatus.bst_date <= end_date,
            FactNotificationStatus.key_type != KEY_TYPE_TEST,
            FactNotificationStatus.notification_status != NOTIFICATION_CANCELLED,
        )
        .group_by(
            FactNotificationStatus.template_id,
            Template.name,
            Template.template_type,
            Template.is_precompiled_letter,
            extract("month", FactNotificationStatus.bst_date).label("month"),
            extract("year", FactNotificationStatus.bst_date).label("year"),
        )
        .order_by(
            extract("year", FactNotificationStatus.bst_date),
            extract("month", FactNotificationStatus.bst_date),
            Template.name,
        )
    )

    if start_date <= datetime.utcnow() <= end_date:
        today = get_london_midnight_in_utc(datetime.utcnow())
        month = get_london_month_from_utc_column(Notification.created_at)

        stats_for_today = (
            db.session.query(
                Notification.template_id.label("template_id"),
                Template.name.label("name"),
                Template.template_type.label("template_type"),
                Template.is_precompiled_letter.label("is_precompiled_letter"),
                extract("month", month).label("month"),
                extract("year", month).label("year"),
                func.count().label("count"),
            )
            .join(
                Template,
                Notification.template_id == Template.id,
            )
            .filter(
                Notification.created_at >= today,
                Notification.service_id == service_id,
                Notification.key_type != KEY_TYPE_TEST,
                Notification.status != NOTIFICATION_CANCELLED,
            )
            .group_by(Notification.template_id, Template.hidden, Template.name, Template.template_type, month)
        )

        all_stats_table = stats.union_all(stats_for_today).subquery()
        query = (
            db.session.query(
                all_stats_table.c.template_id,
                all_stats_table.c.name,
                all_stats_table.c.is_precompiled_letter,
                all_stats_table.c.template_type,
                func.cast(all_stats_table.c.month, Integer).label("month"),
                func.cast(all_stats_table.c.year, Integer).label("year"),
                func.cast(func.sum(all_stats_table.c.count), Integer).label("count"),
            )
            .group_by(
                all_stats_table.c.template_id,
                all_stats_table.c.name,
                all_stats_table.c.is_precompiled_letter,
                all_stats_table.c.template_type,
                all_stats_table.c.month,
                all_stats_table.c.year,
            )
            .order_by(all_stats_table.c.year, all_stats_table.c.month, all_stats_table.c.name)
        )
    else:
        query = stats
    return query.all()


def get_total_notifications_for_date_range(start_date, end_date):
    query = (
        db.session.query(
            FactNotificationStatus.bst_date.cast(db.Text).label("bst_date"),
            func.sum(
                case(
                    (FactNotificationStatus.notification_type == "email", FactNotificationStatus.notification_count),
                    else_=0,
                )
            ).label("emails"),
            func.sum(
                case(
                    (FactNotificationStatus.notification_type == "sms", FactNotificationStatus.notification_count),
                    else_=0,
                )
            ).label("sms"),
            func.sum(
                case(
                    (FactNotificationStatus.notification_type == "letter", FactNotificationStatus.notification_count),
                    else_=0,
                )
            ).label("letters"),
        )
        .filter(
            FactNotificationStatus.key_type != KEY_TYPE_TEST,
        )
        .group_by(FactNotificationStatus.bst_date)
        .order_by(FactNotificationStatus.bst_date)
    )
    if start_date and end_date:
        query = query.filter(FactNotificationStatus.bst_date >= start_date, FactNotificationStatus.bst_date <= end_date)
    return query.all()


@retryable_query()
def fetch_monthly_notification_statuses_per_service(
    start_date, end_date, session: Session | scoped_session = db.session
):
    return (
        session.query(
            func.date_trunc("month", FactNotificationStatus.bst_date).cast(Date).label("date_created"),
            Service.id.label("service_id"),
            Service.name.label("service_name"),  # type: ignore[attr-defined]
            FactNotificationStatus.notification_type,
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status.in_([NOTIFICATION_SENDING, NOTIFICATION_PENDING]),
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_sending"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status == NOTIFICATION_DELIVERED,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_delivered"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status.in_(
                            [NOTIFICATION_TECHNICAL_FAILURE, NOTIFICATION_FAILED]
                        ),
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_technical_failure"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status == NOTIFICATION_TEMPORARY_FAILURE,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_temporary_failure"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status == NOTIFICATION_PERMANENT_FAILURE,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_permanent_failure"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status == NOTIFICATION_SENT,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_sent"),
        )
        .join(Service, FactNotificationStatus.service_id == Service.id)
        .filter(
            FactNotificationStatus.notification_status != NOTIFICATION_CREATED,
            Service.active.is_(True),
            FactNotificationStatus.key_type != KEY_TYPE_TEST,
            Service.restricted.is_(False),
            FactNotificationStatus.bst_date >= start_date,
            FactNotificationStatus.bst_date <= end_date,
        )
        .group_by(
            Service.id,
            Service.name,
            func.date_trunc("month", FactNotificationStatus.bst_date).cast(Date),
            FactNotificationStatus.notification_type,
        )
        .order_by(
            func.date_trunc("month", FactNotificationStatus.bst_date).cast(Date),
            Service.id,
            FactNotificationStatus.notification_type,
        )
        .all()
    )
