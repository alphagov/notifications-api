import itertools
from functools import wraps

from app import db
from app.history_meta import create_history


def autocommit(func):
    @wraps(func)
    def commit_or_rollback(*args, **kwargs):
        try:
            _autocommit = kwargs.pop("_autocommit", True)
            result = func(*args, **kwargs)
            if _autocommit:
                db.session.commit()
            return result
        except Exception:
            db.session.rollback()
            raise

    return commit_or_rollback


class VersionOptions:
    def __init__(self, model_class, history_class=None, must_write_history=True):
        self.model_class = model_class
        self.history_class = history_class
        self.must_write_history = must_write_history


def version_class(*version_options):
    if len(version_options) == 1 and not isinstance(version_options[0], VersionOptions):
        version_options = (VersionOptions(version_options[0]),)

    def versioned(func):
        @wraps(func)
        def record_version(*args, **kwargs):
            func(*args, **kwargs)

            session_objects = []

            for version_option in version_options:
                tmp_session_objects = [
                    (session_object, version_option.history_class)
                    for session_object in itertools.chain(db.session.new, db.session.dirty)
                    if isinstance(session_object, version_option.model_class)
                ]

                if tmp_session_objects == [] and version_option.must_write_history:
                    raise RuntimeError(
                        f"Can't record history for {version_option.model_class.__name__} "
                        "(something in your code has casued the database to "
                        "flush the session early so there's nothing to "
                        "copy into the history table)"
                    )

                session_objects += tmp_session_objects

            for session_object, history_class in session_objects:
                db.session.add(create_history(session_object, history_cls=history_class))

        return record_version

    return versioned


def dao_rollback():
    db.session.rollback()


@autocommit
def dao_save_object(obj):
    # add/update object in db
    db.session.add(obj)
