import itertools
from functools import wraps
from app.history_meta import versioned_objects, create_history


def transactional(func):
    @wraps(func)
    def commit_or_rollback(*args, **kwargs):
        from flask import current_app
        from app import db
        try:
            res = func(*args, **kwargs)
            db.session.commit()
            return res
        except Exception as e:
            current_app.logger.error(e)
            db.session.rollback()
            raise
    return commit_or_rollback


def version_class(model_class):
    def versioned(func):
        @wraps(func)
        def record_version(*args, **kwargs):
            from app import db
            func(*args, **kwargs)
            history_objects = [create_history(obj) for obj in
                               versioned_objects(itertools.chain(db.session.new, db.session.dirty))
                               if isinstance(obj, model_class)]
            for h_obj in history_objects:
                db.session.add(h_obj)
        return record_version
    return versioned
