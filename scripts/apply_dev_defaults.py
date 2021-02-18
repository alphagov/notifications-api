##!/usr/bin/env python
import os, sys
sys.path.insert(1, os.path.join(sys.path[0], '..'))
from flask import Flask
from app import create_app, db
from app.models import PERMISSION_LIST, User, Permission, Service, ProviderDetails, ServiceSmsSender

flask_app = Flask('app')
app = create_app(flask_app)
app.app_context().push() # binds SQLAlchemy to our app instance

# Add all permissions to the seeded user
# These permissions are sent to `notifications-admin` app and unlocks all functionality
user = User.query.filter_by(email_address="notify-service-user@digital.cabinet-office.gov.uk").first()
service = Service.query.first()

if user and service:
  existing_permissions = user.get_permissions()[str(service.id)]

  for permission_name in PERMISSION_LIST:
    if permission_name in existing_permissions:
      continue
    permission = Permission(user_id=user.id, service_id=service.id, permission=permission_name)
    db.session.add(permission)
    db.session.commit()


# SMS Backend Providers: Disable MMG and enable Firetext
# It's easier to open a Firetext account so this seems like a better default.
mmg = ProviderDetails.query.filter_by(identifier='mmg').first()
firetext = ProviderDetails.query.filter_by(identifier='firetext').first()
if mmg:
  mmg.active = False
if firetext:
  firetext.active = True
db.session.commit()

# Disable sending SMS messages as "GOVUK"
# Trying to send an SMS as "GOVUK" will almost certainly get your SMS account blocked
# Let's archive the "GOVUK" sender so it won't be used but sticks around for reference
sender = ServiceSmsSender.query.filter_by(sms_sender='GOVUK').first()
if sender:
  sender.archived = True
  db.session.commit()

# Reset the (randomly generated) password for the default user to a known value
user = User.query.filter_by(email_address="notify-service-user@digital.cabinet-office.gov.uk").first()
new_password = "hu1aX@UgArA6pZ@*^wQW"
user.password = new_password
db.session.commit()
print("\n\nYou can now login the notifactions-admin app using the following credentials:\nEmail: {}\nPassword: {}".format(user.email_address, new_password))
