##!/usr/bin/env python
from app.openapi_swagger import swagger_html_string
from app.performance import init_performance_monitoring

init_performance_monitoring()

from app import create_app  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

application = NotifyApiFlaskApp(
    "app",
    security_schemes={
        "jwt": {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "Enter your GOV.UK Notify API Key. "
                "This is used to generate short-lived JWT to authenticate each request."
            ),
        },
        "admin": {
            "type": "http",
            "scheme": "basic",
            "description": (
                "Not actually basic auth - it's JWT bearer auth. Abusing this to generate the JWTs. "
                "Enter <ADMIN_CLIENT_USER_NAME> as the username and <ADMIN_CLIENT_SECRET> as the password. "
                "These are used to generate short-lived JWT to authenticate each request."
            ),
        },
    },
    ui_templates={"swagger": swagger_html_string},
)

create_app(application)
