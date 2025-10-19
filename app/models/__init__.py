from app import db

_import_bind_key = None

from app.models.default import *

# if db.init_app() hasn't run by this point, the bulk metadata (required for the
# following import) won't have been created yet
if "bulk" not in db.metadatas:
    db._make_metadata("bulk")

_import_bind_key = "bulk"

import app.models.bulk as bulk
