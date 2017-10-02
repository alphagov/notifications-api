import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from flask_script import Command, Option

from app import db
from app.dao.monthly_billing_dao import (
    create_or_update_monthly_billing,
    get_monthly_billing_by_notification_type,
    get_service_ids_that_need_billing_populated
)
from app.models import PROVIDERS, User, SMS_TYPE, EMAIL_TYPE
from app.dao.services_dao import (
    delete_service_and_all_associated_db_objects,
    dao_fetch_all_services_by_user
)
from app.dao.provider_rates_dao import create_provider_rates
from app.dao.users_dao import (delete_model_user, delete_user_verify_codes)
from app.utils import get_midnight_for_day_before, get_london_midnight_in_utc
from app.performance_platform.processing_time import send_processing_time_for_start_and_end


class CreateProviderRateCommand(Command):

    option_list = (
        Option('-p', '--provider_name', dest="provider_name", help='Provider name'),
        Option('-c', '--cost', dest="cost", help='Cost (pence) per message including decimals'),
        Option('-d', '--valid_from', dest="valid_from", help="Date (%Y-%m-%dT%H:%M:%S) valid from")
    )

    def run(self, provider_name, cost, valid_from):
        if provider_name not in PROVIDERS:
            raise Exception("Invalid provider name, must be one of ({})".format(', '.join(PROVIDERS)))

        try:
            cost = Decimal(cost)
        except:
            raise Exception("Invalid cost value.")

        try:
            valid_from = datetime.strptime('%Y-%m-%dT%H:%M:%S', valid_from)
        except:
            raise Exception("Invalid valid_from date. Use the format %Y-%m-%dT%H:%M:%S")

        create_provider_rates(provider_name, valid_from, cost)


class PurgeFunctionalTestDataCommand(Command):

    option_list = (
        Option('-u', '-user-email-prefix', dest='user_email_prefix', help="Functional test user email prefix."),
    )

    def run(self, user_email_prefix=None):
        if user_email_prefix:
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


class CustomDbScript(Command):

    option_list = (
        Option('-n', '-name-of-db-function', dest='name_of_db_function', help="Function name of the DB script to run"),
    )

    def run(self, name_of_db_function):
        db_function = getattr(self, name_of_db_function, None)
        if callable(db_function):
            db_function()
        else:
            print('The specified function does not exist.')

    def backfill_notification_statuses(self):
        """
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

    def update_notification_international_flag(self):
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

    def fix_notification_statuses_not_in_sync(self):
        """
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

    def link_inbound_numbers_to_service(self):
        update = """
        UPDATE inbound_numbers SET
        service_id = services.id,
        updated_at = now()
        FROM services
        WHERE services.sms_sender = inbound_numbers.number AND
        inbound_numbers.service_id is null
        """
        result = db.session.execute(update)
        db.session.commit()

        print("Linked {} inbound numbers to service".format(result.rowcount))


class PopulateMonthlyBilling(Command):
    option_list = (
        Option('-y', '-year', dest="year", help="Use for integer value for year, e.g. 2017"),
    )

    def run(self, year):
        service_ids = get_service_ids_that_need_billing_populated(
            start_date=datetime(2016, 5, 1), end_date=datetime(2017, 8, 16)
        )
        start, end = 1, 13
        if year == '2016':
            start = 4

        for service_id in service_ids:
            print('Starting to populate data for service {}'.format(str(service_id)))
            print('Starting populating monthly billing for {}'.format(year))
            for i in range(start, end):
                print('Population for {}-{}'.format(i, year))
                self.populate(service_id, year, i)

    def populate(self, service_id, year, month):
        create_or_update_monthly_billing(service_id, datetime(int(year), int(month), 1))
        sms_res = get_monthly_billing_by_notification_type(
            service_id, datetime(int(year), int(month), 1), SMS_TYPE
        )
        email_res = get_monthly_billing_by_notification_type(
            service_id, datetime(int(year), int(month), 1), EMAIL_TYPE
        )
        print("Finished populating data for {} for service id {}".format(month, str(service_id)))
        print('SMS: {}'.format(sms_res.monthly_totals))
        print('Email: {}'.format(email_res.monthly_totals))


class BackfillProcessingTime(Command):
    option_list = (
        Option('-s', '--start_date', dest='start_date', help="Date (%Y-%m-%d) start date inclusive"),
        Option('-e', '--end_date', dest='end_date', help="Date (%Y-%m-%d) end date inclusive"),
    )

    def run(self, start_date, end_date):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

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


class PopulateServiceEmailReplyTo(Command):

    def run(self):
        services_to_update = """
            INSERT INTO service_email_reply_to(id, service_id, email_address, is_default, created_at)
            SELECT uuid_in(md5(random()::text || now()::text)::cstring), id, reply_to_email_address, true, '{}'
            FROM services
            WHERE reply_to_email_address IS NOT NULL
            AND id NOT IN(
                SELECT service_id
                FROM service_email_reply_to
            )
        """.format(datetime.utcnow())

        result = db.session.execute(services_to_update)
        db.session.commit()

        print("Populated email reply to adderesses for {}".format(result.rowcount))


class PopulateServiceSmsSender(Command):

    def run(self):
        services_to_update = """
            INSERT INTO service_sms_senders(id, service_id, sms_sender, inbound_number_id, is_default, created_at)
            SELECT uuid_in(md5(random()::text || now()::text)::cstring), service_id, number, id, true, '{}'
            FROM inbound_numbers
            WHERE service_id NOT IN(
                SELECT service_id
                FROM service_sms_senders
            )
        """.format(datetime.utcnow())

        services_to_update_from_services = """
            INSERT INTO service_sms_senders(id, service_id, sms_sender, inbound_number_id, is_default, created_at)
            SELECT uuid_in(md5(random()::text || now()::text)::cstring), id, sms_sender, null, true, '{}'
            FROM services
            WHERE id NOT IN(
                SELECT service_id
                FROM service_sms_senders
            )
        """.format(datetime.utcnow())

        result = db.session.execute(services_to_update)
        second_result = db.session.execute(services_to_update_from_services)
        db.session.commit()

        services_count_query = db.session.execute("Select count(*) from services").fetchall()[0][0]

        service_sms_sender_count_query = db.session.execute("Select count(*) from service_sms_senders").fetchall()[0][0]

        print("Populated sms sender {} services from inbound_numbers".format(result.rowcount))
        print("Populated sms sender {} services from services".format(second_result.rowcount))
        print("{} services in table".format(services_count_query))
        print("{} service_sms_senders".format(service_sms_sender_count_query))


class PopulateServiceLetterContact(Command):

    def run(self):
        services_to_update = """
            INSERT INTO service_letter_contacts(id, service_id, contact_block, is_default, created_at)
            SELECT uuid_in(md5(random()::text || now()::text)::cstring), id, letter_contact_block, true, '{}'
            FROM services
            WHERE letter_contact_block IS NOT NULL
            AND id NOT IN(
                SELECT service_id
                FROM service_letter_contacts
            )
        """.format(datetime.utcnow())

        result = db.session.execute(services_to_update)
        db.session.commit()

        print("Populated letter contacts for {} services".format(result.rowcount))
