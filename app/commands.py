import uuid
from datetime import datetime
from decimal import Decimal
from flask.ext.script import Command, Manager, Option


from app import db
from app.dao.monthly_billing_dao import create_or_update_monthly_billing_sms, get_monthly_billing_sms
from app.models import (PROVIDERS, User)
from app.dao.services_dao import (
    delete_service_and_all_associated_db_objects,
    dao_fetch_all_services_by_user
)
from app.dao.provider_rates_dao import create_provider_rates
from app.dao.users_dao import (delete_model_user, delete_user_verify_codes)


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

    def run(self, service_name_prefix=None, user_email_prefix=None):
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


class PopulateMonthlyBilling(Command):
        option_list = (
            Option('-s', '-service-id', dest='service_id',
                   help="Service id to populate monthly billing for"),
            Option('-y', '-year', dest="year", help="Use for integer value for year, e.g. 2017")
        )

        def run(self, service_id, year):
            start, end = 1, 13
            if year == '2016':
                start = 6

            print('Starting populating monthly billing for {}'.format(year))
            for i in range(start, end):
                self.populate(service_id, year, i)

        def populate(self, service_id, year, month):
            create_or_update_monthly_billing_sms(service_id, datetime(int(year), int(month), 1))
            results = get_monthly_billing_sms(service_id, datetime(int(year), int(month), 1))
            print("Finished populating data for {} for service id {}".format(month, service_id))
            print(results.monthly_totals)
