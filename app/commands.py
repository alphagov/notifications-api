from datetime import datetime
from decimal import Decimal
from flask.ext.script import Command, Manager, Option
from app.models import PROVIDERS
from app.dao.provider_rates_dao import create_provider_rates


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
