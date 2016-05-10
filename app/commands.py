import uuid
from datetime import datetime
from decimal import Decimal
from flask.ext.script import Command, Manager, Option
from app.models import (PROVIDERS, Service, User)
from app.dao.services_dao import delete_service_and_all_associated_db_objects
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
        Option('-n', '-service-name-prefix', dest="service_name_prefix", help='Functional service name prefix.'),
        Option('-u', '-user-email-prefix', dest='user_email_prefix', help="Functional test user email prefix.")
    )

    def run(self, service_name_prefix=None, user_email_prefix=None):
        if service_name_prefix:
            services = Service.query.filter(Service.name.like("{}%".format(service_name_prefix))).all()
            for service in services:
                # Make sure the second part of the service name is a uuid.
                # Just in case someone decides to create a service with that name included in it.
                try:
                    uuid.UUID(service.name.split(service_name_prefix)[1])
                except ValueError:
                    print("Skipping {} as the service name doesn't contain a UUID.".format(service.name))
                else:
                    delete_service_and_all_associated_db_objects(service)
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
                    delete_user_verify_codes(usr)
                    delete_model_user(usr)
