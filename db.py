from flask.ext.script import Manager, Server
from flask_migrate import Migrate, MigrateCommand
from app import create_app, db
from credstash import getAllSecrets
import os

# On AWS get secrets and export to env, skip this on Cloud Foundry
if os.getenv('VCAP_SERVICES') is None:
    os.environ.update(getAllSecrets(region="eu-west-1"))

application = create_app()

manager = Manager(application)
migrate = Migrate(application, db)
manager.add_command('db', MigrateCommand)

if __name__ == '__main__':
    manager.run()
