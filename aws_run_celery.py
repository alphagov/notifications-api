#!/usr/bin/env python
from app import notify_celery, create_app
from credstash import getAllSecrets
import os

# on aws get secrets and export to env
os.environ.update(getAllSecrets(region="eu-west-1"))

application = create_app("delivery")
application.app_context().push()
