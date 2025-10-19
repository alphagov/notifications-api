from app import db

_import_bind_key = None

from app.models.default import *

if "bulk" not in db.metadatas:
    db._make_metadata("bulk")

_import_bind_key = "bulk"

import app.models.bulk as bulk
