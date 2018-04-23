import sys
import functools
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import click
import flask
from click_datetime import Datetime as click_dt
from flask import current_app
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import func
from notifications_utils.statsd_decorators import statsd

from app import db, DATETIME_FORMAT, encryption, redis_store
from app.celery.scheduled_tasks import send_total_sent_notifications_to_performance_platform
from app.celery.service_callback_tasks import send_delivery_status_to_service
from app.celery.letters_pdf_tasks import create_letters_pdf
from app.config import QueueNames
from app.dao.monthly_billing_dao import (
    create_or_update_monthly_billing,
    get_monthly_billing_by_notification_type,
    get_service_ids_that_need_billing_populated
)
from app.dao.provider_rates_dao import create_provider_rates as dao_create_provider_rates
from app.dao.service_callback_api_dao import get_service_callback_api_for_service
from app.dao.services_dao import (
    delete_service_and_all_associated_db_objects,
    dao_fetch_all_services_by_user
)
from app.dao.users_dao import (delete_model_user, delete_user_verify_codes)
from app.models import PROVIDERS, User, SMS_TYPE, EMAIL_TYPE, Notification
from app.performance_platform.processing_time import (send_processing_time_for_start_and_end)
from app.utils import (
    cache_key_for_service_template_usage_per_day,
    get_london_midnight_in_utc,
    get_midnight_for_day_before,
)


@click.group(name='command', help='Additional commands')
def command_group():
    pass


class notify_command:
    def __init__(self, name=None):
        self.name = name

    def __call__(self, func):
        # we need to call the flask with_appcontext decorator to ensure the config is loaded, db connected etc etc.
        # we also need to use functools.wraps to carry through the names and docstrings etc of the functions.
        # Then we need to turn it into a click.Command - that's what command_group.add_command expects.
        @click.command(name=self.name)
        @functools.wraps(func)
        @flask.cli.with_appcontext
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        command_group.add_command(wrapper)

        return wrapper


@notify_command()
@click.option('-p', '--provider_name', required=True, type=click.Choice(PROVIDERS))
@click.option('-c', '--cost', required=True, help='Cost (pence) per message including decimals', type=float)
@click.option('-d', '--valid_from', required=True, type=click_dt(format='%Y-%m-%dT%H:%M:%S'))
def create_provider_rates(provider_name, cost, valid_from):
    """
    Backfill rates for a given provider
    """
    cost = Decimal(cost)
    dao_create_provider_rates(provider_name, valid_from, cost)


@notify_command()
@click.option('-u', '--user_email_prefix', required=True, help="""
    Functional test user email prefix. eg "notify-test-preview"
""")  # noqa
def purge_functional_test_data(user_email_prefix):
    """
    Remove non-seeded functional test data

    users, services, etc. Give an email prefix. Probably "notify-test-preview".
    """
    users = User.query.filter(User.email_address.like("{}%".format(user_email_prefix))).all()
    for usr in users:
        # Make sure the full email includes a uuid in it
        # Just in case someone decides to use a similar email address.
        try:
            uuid.UUID(usr.email_address.split("@")[0].split('+')[1])
        except ValueError:
            print("Skipping {} as the user email doesn't contain a UUID.".format(usr.email_address))
        else:
            services = dao_fetch_all_services_by_user(usr.id)
            if services:
                for service in services:
                    delete_service_and_all_associated_db_objects(service)
            else:
                delete_user_verify_codes(usr)
                delete_model_user(usr)


@notify_command()
def backfill_notification_statuses():
    """
    DEPRECATED. Populates notification_status.

    This will be used to populate the new `Notification._status_fkey` with the old
    `Notification._status_enum`
    """
    LIMIT = 250000
    subq = "SELECT id FROM notification_history WHERE notification_status is NULL LIMIT {}".format(LIMIT)
    update = "UPDATE notification_history SET notification_status = status WHERE id in ({})".format(subq)
    result = db.session.execute(subq).fetchall()

    while len(result) > 0:
        db.session.execute(update)
        print('commit {} updates at {}'.format(LIMIT, datetime.utcnow()))
        db.session.commit()
        result = db.session.execute(subq).fetchall()


@notify_command()
def update_notification_international_flag():
    """
    DEPRECATED. Set notifications.international=false.
    """
    # 250,000 rows takes 30 seconds to update.
    subq = "select id from notifications where international is null limit 250000"
    update = "update notifications set international = False where id in ({})".format(subq)
    result = db.session.execute(subq).fetchall()

    while len(result) > 0:
        db.session.execute(update)
        print('commit 250000 updates at {}'.format(datetime.utcnow()))
        db.session.commit()
        result = db.session.execute(subq).fetchall()

    # Now update notification_history
    subq_history = "select id from notification_history where international is null limit 250000"
    update_history = "update notification_history set international = False where id in ({})".format(subq_history)
    result_history = db.session.execute(subq_history).fetchall()
    while len(result_history) > 0:
        db.session.execute(update_history)
        print('commit 250000 updates at {}'.format(datetime.utcnow()))
        db.session.commit()
        result_history = db.session.execute(subq_history).fetchall()


@notify_command()
def fix_notification_statuses_not_in_sync():
    """
    DEPRECATED.
    This will be used to correct an issue where Notification._status_enum and NotificationHistory._status_fkey
    became out of sync. See 979e90a.

    Notification._status_enum is the source of truth so NotificationHistory._status_fkey will be updated with
    these values.
    """
    MAX = 10000

    subq = "SELECT id FROM notifications WHERE cast (status as text) != notification_status LIMIT {}".format(MAX)
    update = "UPDATE notifications SET notification_status = status WHERE id in ({})".format(subq)
    result = db.session.execute(subq).fetchall()

    while len(result) > 0:
        db.session.execute(update)
        print('Committed {} updates at {}'.format(len(result), datetime.utcnow()))
        db.session.commit()
        result = db.session.execute(subq).fetchall()

    subq_hist = "SELECT id FROM notification_history WHERE cast (status as text) != notification_status LIMIT {}" \
        .format(MAX)
    update = "UPDATE notification_history SET notification_status = status WHERE id in ({})".format(subq_hist)
    result = db.session.execute(subq_hist).fetchall()

    while len(result) > 0:
        db.session.execute(update)
        print('Committed {} updates at {}'.format(len(result), datetime.utcnow()))
        db.session.commit()
        result = db.session.execute(subq_hist).fetchall()


@notify_command()
@click.option('-y', '--year', required=True, help="e.g. 2017", type=int)
@click.option('-s', '--service_id', required=False, help="Enter the service id", type=click.UUID)
@click.option('-m', '--month', required=False, help="e.g. 1 for January", type=int)
def populate_monthly_billing(year, service_id=None, month=None):
    """
    Populate monthly billing table for all services for a given year.
    If service_id and month provided then only rebuild monthly billing for that month.
    """
    def populate(service_id, year, month):
        create_or_update_monthly_billing(service_id, datetime(year, month, 1))
        sms_res = get_monthly_billing_by_notification_type(
            service_id, datetime(year, month, 1), SMS_TYPE
        )
        email_res = get_monthly_billing_by_notification_type(
            service_id, datetime(year, month, 1), EMAIL_TYPE
        )
        letter_res = get_monthly_billing_by_notification_type(
            service_id, datetime(year, month, 1), 'letter'
        )

        print("Finished populating data for {}-{} for service id {}".format(month, year, str(service_id)))
        print('SMS: {}'.format(sms_res.monthly_totals))
        print('Email: {}'.format(email_res.monthly_totals))
        print('Letter: {}'.format(letter_res.monthly_totals))

    if service_id and month:
            populate(service_id, year, month)
    else:
        service_ids = get_service_ids_that_need_billing_populated(
            start_date=datetime(2016, 5, 1), end_date=datetime(2017, 8, 16)
        )
        start, end = 1, 13

        if year == 2016:
            start = 4

        for service_id in service_ids:
            print('Starting to populate data for service {}'.format(str(service_id)))
            print('Starting populating monthly billing for {}'.format(year))
            for i in range(start, end):
                print('Population for {}-{}'.format(i, year))
                populate(service_id, year, i)


@notify_command()
@click.option('-s', '--start_date', required=True, help="start date inclusive", type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help="end date inclusive", type=click_dt(format='%Y-%m-%d'))
def backfill_performance_platform_totals(start_date, end_date):
    """
    Send historical total messages sent to Performance Platform.

    WARNING: This does not overwrite existing data. You need to delete
             the existing data or Performance Platform will double-count.
    """

    delta = end_date - start_date

    print('Sending total messages sent for all days between {} and {}'.format(start_date, end_date))

    for i in range(delta.days + 1):

        process_date = start_date + timedelta(days=i)

        print('Sending total messages sent for {}'.format(
            process_date.isoformat()
        ))

        send_total_sent_notifications_to_performance_platform(process_date)


@notify_command()
@click.option('-s', '--start_date', required=True, help="start date inclusive", type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help="end date inclusive", type=click_dt(format='%Y-%m-%d'))
def backfill_processing_time(start_date, end_date):
    """
    Send historical processing time to Performance Platform.
    """

    delta = end_date - start_date

    print('Sending notification processing-time data for all days between {} and {}'.format(start_date, end_date))

    for i in range(delta.days + 1):
        # because the tz conversion funcs talk about midnight, and the midnight before last,
        # we want to pretend we're running this from the next morning, so add one.
        process_date = start_date + timedelta(days=i + 1)

        process_start_date = get_midnight_for_day_before(process_date)
        process_end_date = get_london_midnight_in_utc(process_date)

        print('Sending notification processing-time for {} - {}'.format(
            process_start_date.isoformat(),
            process_end_date.isoformat()
        ))
        send_processing_time_for_start_and_end(process_start_date, process_end_date)


@notify_command()
def populate_annual_billing():
    """
    add annual_billing for 2016, 2017 and 2018.
    """
    financial_year = [2016, 2017, 2018]

    for fy in financial_year:
        populate_data = """
        INSERT INTO annual_billing(id, service_id, free_sms_fragment_limit, financial_year_start,
                created_at, updated_at)
            SELECT uuid_in(md5(random()::text || now()::text)::cstring), id, 250000, {}, '{}', '{}'
            FROM services
            WHERE id NOT IN(
                SELECT service_id
                FROM annual_billing
                WHERE financial_year_start={})
        """.format(fy, datetime.utcnow(), datetime.utcnow(), fy)

        services_result1 = db.session.execute(populate_data)
        db.session.commit()

        print("Populated annual billing {} for {} services".format(fy, services_result1.rowcount))


@notify_command(name='list-routes')
def list_routes():
    """List URLs of all application routes."""
    for rule in sorted(current_app.url_map.iter_rules(), key=lambda r: r.rule):
        print("{:10} {}".format(", ".join(rule.methods - set(['OPTIONS', 'HEAD'])), rule.rule))


@notify_command(name='insert-inbound-numbers')
@click.option('-f', '--file_name', required=True,
              help="""Full path of the file to upload, file is a contains inbound numbers,
              one number per line. The number must have the format of 07... not 447....""")
def insert_inbound_numbers_from_file(file_name):
    print("Inserting inbound numbers from {}".format(file_name))
    file = open(file_name)
    sql = "insert into inbound_numbers values('{}', '{}', 'mmg', null, True, now(), null);"

    for line in file:
        print(line)
        db.session.execute(sql.format(uuid.uuid4(), line.strip()))
        db.session.commit()
    file.close()


@notify_command(name='replay-create-pdf-letters')
@click.option('-n', '--notification_id', type=click.UUID, required=True,
              help="Notification id of the letter that needs the create_letters_pdf task replayed")
def replay_create_pdf_letters(notification_id):
    print("Create task to create_letters_pdf for notification: {}".format(notification_id))
    create_letters_pdf.apply_async([str(notification_id)], queue=QueueNames.CREATE_LETTERS_PDF)


@notify_command(name='replay-service-callbacks')
@click.option('-f', '--file_name', required=True,
              help="""Full path of the file to upload, file is a contains client references of
              notifications that need the status to be sent to the service.""")
@click.option('-s', '--service_id', required=True,
              help="""The service that the callbacks are for""")
def replay_service_callbacks(file_name, service_id):
    print("Start send service callbacks for service: ", service_id)
    callback_api = get_service_callback_api_for_service(service_id=service_id)
    if not callback_api:
        print("Callback api was not found for service: {}".format(service_id))
        return

    errors = []
    notifications = []
    file = open(file_name)

    for ref in file:
        try:
            notification = Notification.query.filter_by(client_reference=ref.strip()).one()
            notifications.append(notification)
        except NoResultFound as e:
            errors.append("Reference: {} was not found in notifications.".format(ref))

    for e in errors:
        print(e)
    if errors:
        raise Exception("Some notifications for the given references were not found")

    for n in notifications:
        data = {
            "notification_id": str(n.id),
            "notification_client_reference": n.client_reference,
            "notification_to": n.to,
            "notification_status": n.status,
            "notification_created_at": n.created_at.strftime(DATETIME_FORMAT),
            "notification_updated_at": n.updated_at.strftime(DATETIME_FORMAT),
            "notification_sent_at": n.sent_at.strftime(DATETIME_FORMAT),
            "notification_type": n.notification_type,
            "service_callback_api_url": callback_api.url,
            "service_callback_api_bearer_token": callback_api.bearer_token,
        }
        encrypted_status_update = encryption.encrypt(data)
        send_delivery_status_to_service.apply_async([str(n.id), encrypted_status_update],
                                                    queue=QueueNames.CALLBACKS)

    print("Replay service status for service: {}. Sent {} notification status updates to the queue".format(
        service_id, len(notifications)))


def setup_commands(application):
    application.cli.add_command(command_group)


@notify_command(name='migrate-data-to-ft-billing')
@click.option('-s', '--start_date', required=True, help="start date inclusive", type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help="end date inclusive", type=click_dt(format='%Y-%m-%d'))
@statsd(namespace="tasks")
def migrate_data_to_ft_billing(start_date, end_date):

    print('Billing migration from date {} to {}'.format(start_date, end_date))

    process_date = start_date
    total_updated = 0

    while process_date < end_date:

        sql = \
            """
            select count(*) from notification_history where notification_status!='technical-failure'
            and key_type!='test'
            and notification_status!='created'
            and created_at >= (date :start + time '00:00:00') at time zone 'Europe/London' at time zone 'UTC'
            and created_at < (date :end + time '00:00:00') at time zone 'Europe/London' at time zone 'UTC'
            """
        num_notifications = db.session.execute(sql, {"start": process_date,
                                                     "end": process_date + timedelta(days=1)}).fetchall()[0][0]
        sql = \
            """
            select count(*) from
            (select distinct service_id, template_id, rate_multiplier,
            sent_by from notification_history
            where notification_status!='technical-failure'
            and key_type!='test'
            and notification_status!='created'
            and created_at >= (date :start + time '00:00:00') at time zone 'Europe/London' at time zone 'UTC'
            and created_at < (date :end + time '00:00:00') at time zone 'Europe/London' at time zone 'UTC'
            ) as distinct_records
            """

        predicted_records = db.session.execute(sql, {"start": process_date,
                                                     "end": process_date + timedelta(days=1)}).fetchall()[0][0]

        start_time = datetime.now()
        print('ft_billing: Migrating date: {}, notifications: {}, expecting {} ft_billing rows'
              .format(process_date.date(), num_notifications, predicted_records))

        # migrate data into ft_billing, ignore if records already exist - do not do upsert
        sql = \
            """
            insert into ft_billing (bst_date, template_id, service_id, notification_type, provider, rate_multiplier,
                international, billable_units, notifications_sent, rate)
                select bst_date, template_id, service_id, notification_type, provider, rate_multiplier, international,
                    sum(billable_units) as billable_units, sum(notifications_sent) as notification_sent,
                    case when notification_type = 'sms' then sms_rate else letter_rate end as rate
                from (
                    select
                        n.id,
                        da.bst_date,
                        coalesce(n.template_id, '00000000-0000-0000-0000-000000000000') as template_id,
                        coalesce(n.service_id, '00000000-0000-0000-0000-000000000000') as service_id,
                        n.notification_type,
                        coalesce(n.sent_by, (
                        case
                        when notification_type = 'sms' then
                            coalesce(sent_by, 'unknown')
                        when notification_type = 'letter' then
                            coalesce(sent_by, 'dvla')
                        else
                            coalesce(sent_by, 'ses')
                        end )) as provider,
                        coalesce(n.rate_multiplier,1) as rate_multiplier,
                        s.crown,
                        coalesce((select rates.rate from rates
                        where n.notification_type = rates.notification_type and n.sent_at > rates.valid_from
                        order by rates.valid_from desc limit 1), 0) as sms_rate,
                        coalesce((select l.rate from letter_rates l where n.rate_multiplier = l.sheet_count
                        and s.crown = l.crown and n.notification_type='letter'), 0) as letter_rate,
                        coalesce(n.international, false) as international,
                        n.billable_units,
                        1 as notifications_sent
                    from public.notification_history n
                    left join templates t on t.id = n.template_id
                    left join dm_datetime da on n.created_at>= da.utc_daytime_start
                        and n.created_at < da.utc_daytime_end
                    left join services s on s.id = n.service_id
                    where n.notification_status!='technical-failure'
                        and n.key_type!='test'
                        and n.notification_status!='created'
                        and n.created_at >= (date :start + time '00:00:00') at time zone 'Europe/London'
                        at time zone 'UTC'
                        and n.created_at < (date :end + time '00:00:00') at time zone 'Europe/London' at time zone 'UTC'
                    ) as individual_record
                group by bst_date, template_id, service_id, notification_type, provider, rate_multiplier, international,
                    sms_rate, letter_rate
                order by bst_date
            on conflict on constraint ft_billing_pkey do update set
             billable_units = excluded.billable_units,
             notifications_sent = excluded.notifications_sent,
             rate = excluded.rate
            """

        result = db.session.execute(sql, {"start": process_date, "end": process_date + timedelta(days=1)})
        db.session.commit()
        print('ft_billing: --- Completed took {}ms. Migrated {} rows.'.format(datetime.now() - start_time,
                                                                              result.rowcount))
        if predicted_records != result.rowcount:
            print('          : ^^^ Result mismatch by {} rows ^^^'
                  .format(predicted_records - result.rowcount))

        process_date += timedelta(days=1)

        total_updated += result.rowcount
    print('Total inserted/updated records = {}'.format(total_updated))


@notify_command()
@click.option('-s', '--service_id', required=True, type=click.UUID)
@click.option('-d', '--day', required=True, type=click_dt(format='%Y-%m-%d'))
def populate_redis_template_usage(service_id, day):
    """
    Recalculate and replace the stats in redis for a day.
    To be used if redis data is lost for some reason.
    """
    if not current_app.config['REDIS_ENABLED']:
        current_app.logger.error('Cannot populate redis template usage - redis not enabled')
        sys.exit(1)

    # the day variable is set by click to be midnight of that day
    start_time = get_london_midnight_in_utc(day)
    end_time = get_london_midnight_in_utc(day + timedelta(days=1))

    usage = {
        str(row.template_id): row.count
        for row in db.session.query(
            Notification.template_id,
            func.count().label('count')
        ).filter(
            Notification.service_id == service_id,
            Notification.created_at >= start_time,
            Notification.created_at < end_time
        ).group_by(
            Notification.template_id
        )
    }
    current_app.logger.info('Populating usage dict for service {} day {}: {}'.format(
        service_id,
        day,
        usage.items())
    )
    if usage:
        key = cache_key_for_service_template_usage_per_day(service_id, day)
        redis_store.set_hash_and_expire(
            key,
            usage,
            current_app.config['EXPIRE_CACHE_EIGHT_DAYS'],
            raise_exception=True
        )
