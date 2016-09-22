import logging

from flask import current_app

from app.clients.sms.firetext import (
    FiretextClient
)

logger = logging.getLogger(__name__)


class LoadtestingClient(FiretextClient):
    '''
    Loadtest sms client.
    '''

    def init_app(self, config, statsd_client, *args, **kwargs):
        super(FiretextClient, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self.api_key = config.config.get('LOADTESTING_API_KEY')
        self.from_number = config.config.get('LOADTESTING_NUMBER')
        self.name = 'loadtesting'
        self.url = "https://www.firetext.co.uk/api/sendsms/json"
        self.statsd_client = statsd_client
