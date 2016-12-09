#!/usr/bin/env python
from app import notify_celery, create_app
from credstash import getAllSecrets
import os

# On AWS get secrets and export to env, skip this on Cloud Foundry
if os.getenv('VCAP_SERVICES') is None:
    os.environ.update(getAllSecrets(region="eu-west-1"))

application = create_app("delivery")
application.app_context().push()
