#!/usr/bin/env python
from app import notify_celery, create_app
from credstash import getAllSecrets
import os
from config import configs

default_env_file = '/home/ubuntu/environment'
environment = 'live'

if os.path.isfile(default_env_file):
    environment_file = open(default_env_file, 'r')
    environment = environment_file.readline().strip()

# on aws get secrets and export to env
secrets = getAllSecrets(region="eu-west-1")
for key, val in secrets.items():
    os.environ[key] = val

os.environ['NOTIFY_API_ENVIRONMENT'] = configs[environment]

application = create_app()
application.app_context().push()
