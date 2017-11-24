#!/usr/bin/env python
# notify_celery is referenced from manifest_delivery_base.yml, and cannot be removed
from flask import Flask

from app import notify_celery, create_app


application = Flask('delivery')
create_app(application)
application.app_context().push()
