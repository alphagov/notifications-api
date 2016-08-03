from flask.ext.script import Manager, Server
from flask_migrate import Migrate, MigrateCommand
from app import create_app, db
from credstash import getAllSecrets
import os

# on aws get secrets and export to env
os.environ.update(getAllSecrets(region="eu-west-1"))

print("DOING SETUP")
print("\n" * 10)
print("SECRETS")
print("\n" * 10)
print(getAllSecrets(region="eu-west-1"))
print("\n" * 10)
print("ENV")
print("\n" * 10)
print(os.environ)

application = create_app()

manager = Manager(application)
migrate = Migrate(application, db)
manager.add_command('db', MigrateCommand)

if __name__ == '__main__':
    manager.run()
