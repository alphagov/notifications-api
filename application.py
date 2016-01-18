#!/usr/bin/env python

from __future__ import print_function

import os

from flask.ext.script import Manager, Server
from flask.ext.migrate import Migrate, MigrateCommand

from app import create_app, db

application = create_app(os.getenv('NOTIFY_API_ENVIRONMENT') or 'development')
manager = Manager(application)
port = int(os.environ.get('PORT', 6011))
manager.add_command("runserver", Server(host='0.0.0.0', port=port))

migrate = Migrate(application, db)
manager.add_command('db', MigrateCommand)


@manager.command
def list_routes():
    """List URLs of all application routes."""
    for rule in sorted(application.url_map.iter_rules(), key=lambda r: r.rule):
        print("{:10} {}".format(", ".join(rule.methods - set(['OPTIONS', 'HEAD'])), rule.rule))


@manager.command
def create_admin_user_service():
    """
    Convience method to create a admin user and service
    :return: API token for admin service
    """
    from app.models import User, Service, Token
    from app.dao import tokens_dao, users_dao, services_dao
    from flask import current_app

    user = User(**{'email_address': current_app.config['ADMIN_USER_EMAIL_ADDRESS']})
    users_dao.save_model_user(user)

    service = Service(**{'name': 'Notify Service Admin',
                         'users':[user],
                         'limit': 1000,
                         'active': True,
                         'restricted': True})
    services_dao.save_model_service(service)
    token = Token(**{'service_id': service.id})
    tokens_dao.save_model_token(token)
    print('Token: {}'.format(tokens_dao.get_unsigned_token(service.id)))


if __name__ == '__main__':
    manager.run()
