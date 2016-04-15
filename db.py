from flask.ext.script import Manager, Server
from flask_migrate import Migrate, MigrateCommand
from app import create_app, db
from credstash import getAllSecrets
import os

default_env_file = '/home/notify-app/environment'
environment = 'live'

if os.path.isfile(default_env_file):
    with open(default_env_file, 'r') as environment_file:
        environment = environment_file.readline().strip()

# on aws get secrets and export to env
os.environ.update(getAllSecrets(region="eu-west-1"))

from config import configs

os.environ['NOTIFY_API_ENVIRONMENT'] = configs[environment]

application = create_app()

manager = Manager(application)
migrate = Migrate(application, db)
manager.add_command('db', MigrateCommand)

if __name__ == '__main__':
    manager.run()
