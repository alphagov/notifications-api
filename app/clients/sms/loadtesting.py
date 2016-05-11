import logging
from app.clients.sms.firetext import (
    FiretextClient
)

logger = logging.getLogger(__name__)


class LoadtestingClient(FiretextClient):
    '''
    Loadtest sms client.
    '''

    def init_app(self, config, *args, **kwargs):
        super(FiretextClient, self).__init__(*args, **kwargs)
        self.api_key = config.config.get('LOADTESTING_API_KEY')
        self.from_number = config.config.get('LOADTESTING_NUMBER')
        self.name = 'loadtesting'
