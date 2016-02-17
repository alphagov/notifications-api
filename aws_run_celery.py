#!/usr/bin/env python
from app import notify_celery, create_app
from credstash import getAllSecrets
import os

# on aws get secrets and export to env
secrets = getAllSecrets(region="eu-west-1")
for key, val in secrets.items():
    os.environ[key] = val

application = create_app()
application.app_context().push()
