from flask_migrate import Migrate, MigrateCommand
from app import (create_app, db, commands)
import os

default_env_file = '/home/ubuntu/environment'
environment = 'live'

if os.path.isfile(default_env_file):
    with open(default_env_file, 'r') as environment_file:
        environment = environment_file.readline().strip()

from app.config import configs

os.environ['NOTIFY_API_ENVIRONMENT'] = configs[environment]

application = create_app()

migrate = Migrate(application, db)
application.add_command('db', MigrateCommand)
application.add_command('purge_functional_test_data', commands.PurgeFunctionalTestDataCommand)
application.add_command('custom_db_script', commands.CustomDbScript)

if __name__ == '__main__':
    manager.run()
