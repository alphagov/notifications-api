#!/usr/bin/env python

from __future__ import print_function
import os
from flask.ext.script import Manager, Server
from flask.ext.migrate import Migrate, MigrateCommand
from app import (create_app, db, commands)

application = create_app()
manager = Manager(application)
port = int(os.environ.get('PORT', 6011))
manager.add_command("runserver", Server(host='0.0.0.0', port=port))

migrate = Migrate(application, db)
manager.add_command('db', MigrateCommand)
manager.add_command('create_provider_rate', commands.CreateProviderRateCommand)
manager.add_command('purge_functional_test_data', commands.PurgeFunctionalTestDataCommand)
manager.add_command('custom_db_script', commands.CustomDbScript)


@manager.command
def list_routes():
    """List URLs of all application routes."""
    for rule in sorted(application.url_map.iter_rules(), key=lambda r: r.rule):
        print("{:10} {}".format(", ".join(rule.methods - set(['OPTIONS', 'HEAD'])), rule.rule))


if __name__ == '__main__':
    manager.run()
