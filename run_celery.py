#!/usr/bin/env python
import os
from app import celery, create_app
from app.celery.tasks import refresh_services

application = create_app(os.getenv('NOTIFY_API_ENVIRONMENT') or 'development')
application.app_context().push()
