#!/usr/bin/env python

import os

if (environment := os.getenv("NOTIFY_ENVIRONMENT")) in {"development", "preview", "staging"} and os.getenv(
    "NEW_RELIC_ENABLED"
) == "1":
    import newrelic.agent

    # Expects NEW_RELIC_LICENSE_KEY set in environment as well.
    newrelic.agent.initialize("newrelic.ini", environment=environment, ignore_errors=False)

# import prometheus before any other code. If gds_metrics is imported first it will write a prometheus file to disk
# that will never be read from (since we don't have prometheus celery stats). If prometheus is imported first,
# prometheus will simply store the metrics in memory
import prometheus_client  # noqa

# We have lots of issues related to using pycurl locally on (M1?) macs.
# We have specific installation instructions for pycurl here:
#   https://github.com/alphagov/notifications-manuals/wiki/Getting-started#pycurl
# However this sometimes still doesn't seem to be enough for pycurl when running the celery workers.
# Importing pycurl here - notably before the import at kombu.asynchronous.http.curl:15 - seems to mitigate the error
# I've seen a lot lately:
#   ImportError: pycurl: libcurl link-time version (7.76.1) is older than compile-time version (7.85.0)
# See https://github.com/alphagov/notifications-api/pull/3687 for a little more of the investigation/notes
import pycurl  # noqa: F401

# notify_celery is referenced from manifest_delivery_base.yml, and cannot be removed
from app import create_app, notify_celery  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("delivery")
create_app(application)
application.app_context().push()
