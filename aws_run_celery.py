#!/usr/bin/env python
from app import create_app

application = create_app("delivery")
application.app_context().push()
