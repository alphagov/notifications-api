from app import db

# _import_bind_key is used as something analogous to an "argument" for the import
# of `default.py`, allowing us to "bind" the models to a different sqlalchemy
# metadata each time it's imported via a different aliased path
_import_bind_key = None

from app.models.default import *  # noqa

# if db.init_app() hasn't run by this point, the bulk metadata (required for the
# following import) won't have been created yet
if "bulk" not in db.metadatas:
    db._make_metadata("bulk")  # APIFRAGILE

_import_bind_key = "bulk"

import app.models.bulk as bulk  # noqa
