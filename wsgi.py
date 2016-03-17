import os

from app import create_app
from credstash import getAllSecrets


default_env_file = '/home/ubuntu/environment'
environment = 'live'

if os.path.isfile(default_env_file):
    with open(default_env_file, 'r') as environment_file:
        environment = environment_file.readline().strip()

# on aws get secrets and export to env
os.environ.update(getAllSecrets(region="eu-west-1"))

from config import configs

os.environ['NOTIFY_API_ENVIRONMENT'] = configs[environment]

application = create_app()

if __name__ == "__main__":
    application.run()
