#!/usr/bin/env python
# notify_celery is referenced from manifest_delivery_base.yml, and cannot be removed
from app import notify_celery, create_app

application = create_app('delivery')
application.app_context().push()
