from flask.ext.script import Manager, Server
from flask_migrate import Migrate, MigrateCommand
from app import (create_app, db, commands)
from credstash import getAllSecrets
import os

default_env_file = '/home/ubuntu/environment'
environment = 'live'

if os.path.isfile(default_env_file):
    with open(default_env_file, 'r') as environment_file:
        environment = environment_file.readline().strip()

# On AWS get secrets and export to env, skip this on Cloud Foundry
if os.getenv('VCAP_SERVICES') is None:
    os.environ.update(getAllSecrets(region="eu-west-1"))

from app.config import configs

os.environ['NOTIFY_API_ENVIRONMENT'] = configs[environment]

application = create_app()

manager = Manager(application)
migrate = Migrate(application, db)
manager.add_command('db', MigrateCommand)
manager.add_command('purge_functional_test_data', commands.PurgeFunctionalTestDataCommand)

if __name__ == '__main__':
    manager.run()
