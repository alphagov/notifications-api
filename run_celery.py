#!/usr/bin/env python
from app import notify_celery, create_app

application = create_app()
application.app_context().push()
