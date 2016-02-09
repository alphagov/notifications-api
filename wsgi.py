from app import create_app
from credstash import getAllSecrets
import os

config = 'live'
default_env_file = '/home/ubuntu/environment'

if os.path.isfile(default_env_file):
        environment = open(default_env_file, 'r')
        config = environment.readline().strip()

secrets = getAllSecrets(region="eu-west-1")

application = create_app(config, secrets)

if __name__ == "__main__":
        application.run()
