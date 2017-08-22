"""
Extracts cloudfoundry config from its json and populates the environment variables that we would expect to be populated
on local/aws boxes
"""

import os
import json


def extract_cloudfoundry_config():
    vcap_services = json.loads(os.environ['VCAP_SERVICES'])
    set_config_env_vars(vcap_services)


def set_config_env_vars(vcap_services):
    # Postgres config
    os.environ['SQLALCHEMY_DATABASE_URI'] = vcap_services['postgres'][0]['credentials']['uri']

    vcap_application = json.loads(os.environ['VCAP_APPLICATION'])
    os.environ['NOTIFY_ENVIRONMENT'] = vcap_application['space_name']
    os.environ['NOTIFY_LOG_PATH'] = '/home/vcap/logs/app.log'

    # Notify common config
    for s in vcap_services['user-provided']:
        if s['name'] == 'notify-config':
            extract_notify_config(s)
        elif s['name'] == 'notify-aws':
            extract_notify_aws_config(s)
        elif s['name'] == 'hosted-graphite':
            extract_hosted_graphite_config(s)
        elif s['name'] == 'mmg':
            extract_mmg_config(s)
        elif s['name'] == 'firetext':
            extract_firetext_config(s)
        elif s['name'] == 'redis':
            extract_redis_config(s)


def extract_notify_config(notify_config):
    os.environ['ADMIN_BASE_URL'] = notify_config['credentials']['admin_base_url']
    os.environ['API_HOST_NAME'] = notify_config['credentials']['api_host_name']
    os.environ['ADMIN_CLIENT_SECRET'] = notify_config['credentials']['admin_client_secret']
    os.environ['SECRET_KEY'] = notify_config['credentials']['secret_key']
    os.environ['DANGEROUS_SALT'] = notify_config['credentials']['dangerous_salt']
    os.environ['PERFORMANCE_PLATFORM_TOKEN'] = notify_config['credentials'].get('performance_platform_token', '')
    os.environ['SMS_INBOUND_WHITELIST'] = json.dumps(notify_config['credentials']['allow_ip_inbound_sms'])


def extract_notify_aws_config(aws_config):
    os.environ['NOTIFICATION_QUEUE_PREFIX'] = aws_config['credentials']['sqs_queue_prefix']
    os.environ['AWS_ACCESS_KEY_ID'] = aws_config['credentials']['aws_access_key_id']
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_config['credentials']['aws_secret_access_key']


def extract_hosted_graphite_config(hosted_graphite_config):
    os.environ['STATSD_PREFIX'] = hosted_graphite_config['credentials']['statsd_prefix']


def extract_mmg_config(mmg_config):
    os.environ['MMG_URL'] = mmg_config['credentials']['api_url']
    os.environ['MMG_API_KEY'] = mmg_config['credentials']['api_key']


def extract_firetext_config(firetext_config):
    os.environ['FIRETEXT_API_KEY'] = firetext_config['credentials']['api_key']
    os.environ['LOADTESTING_API_KEY'] = firetext_config['credentials']['loadtesting_api_key']


def extract_redis_config(redis_config):
    os.environ['REDIS_ENABLED'] = redis_config['credentials']['redis_enabled']
    os.environ['REDIS_URL'] = redis_config['credentials']['redis_url']
