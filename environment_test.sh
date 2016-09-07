#!/bin/bash
export SQLALCHEMY_DATABASE_URI=${TEST_DATABASE:='postgresql://localhost/test_notification_api'}
export SECRET_KEY='secret-key'
export DANGEROUS_SALT='dangerous-salt'
export NOTIFY_ENVIRONMENT='test'
export ADMIN_CLIENT_SECRET='dev-notify-secret-key'
export ADMIN_BASE_URL='http://localhost:6012'
export FROM_NUMBER='from_number'
export MMG_URL="https://api.mmg.co.uk/json/api.php"
export MMG_API_KEY='mmg-secret-key'
export LOADTESTING_API_KEY="loadtesting"
export FIRETEXT_API_KEY="Firetext"
export STATSD_PREFIX="stats-prefix"
