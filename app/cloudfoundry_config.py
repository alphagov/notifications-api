import json
import os


def extract_cloudfoundry_config():
    vcap_services = json.loads(os.environ['VCAP_SERVICES'])

    # Postgres config
    os.environ['SQLALCHEMY_DATABASE_URI'] = vcap_services['postgres'][0]['credentials']['uri'].replace('postgres',
                                                                                                       'postgresql')
    # Redis config
    if 'redis' in vcap_services:
        os.environ['REDIS_URL'] = vcap_services['redis'][0]['credentials']['uri']
