##!/usr/bin/env python
from __future__ import print_function

from flask import Flask

from app import create_app

application = Flask('app')

create_app(application)

1 / 0  # TODO: revert this change
