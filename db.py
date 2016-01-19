from flask.ext.script import Manager, Server
from flask_migrate import Migrate, MigrateCommand
from app import create_app, db
from credstash import getAllSecrets

secrets = getAllSecrets(region="eu-west-1")

application = create_app('live', secrets)

manager = Manager(application)
migrate = Migrate(application, db)
manager.add_command('db', MigrateCommand)

if __name__ == '__main__':
    manager.run()
