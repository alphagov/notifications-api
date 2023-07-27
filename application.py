##!/usr/bin/env python
from app.performance import init_performance_monitoring

init_performance_monitoring()

from app import create_app  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

application = NotifyApiFlaskApp(
    "app",
    security_schemes={
        "jwt": {"type": "http", "scheme": "bearer", "bearerFormat": "Short-lived JSON Web Token (JWT) from API key"},
        "admin": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Short-lived JSON Web Token (JWT) from notify-admin",
        },
    },
)

create_app(application)
