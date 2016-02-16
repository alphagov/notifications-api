#!/usr/bin/env python
import os
from app import notify_celery, create_app

application = create_app(os.getenv('NOTIFY_API_ENVIRONMENT') or 'development')
application.app_context().push()
