import itertools
from functools import wraps
from app.history_meta import versioned_objects, create_history


def transactional(func):
    @wraps(func)
    def commit_or_rollback(*args, **kwargs):
        from flask import current_app
        from app import db
        try:
            func(*args, **kwargs)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(e)
            db.session.rollback()
            raise
    return commit_or_rollback


def versioned(func):
    @wraps(func)
    def record_version(*args, **kwargs):
        from app import db
        func(*args, **kwargs)
        history_objects = [create_history(obj) for obj in
                           versioned_objects(itertools.chain(db.session.new, db.session.dirty))]
        for h_obj in history_objects:
            db.session.add(h_obj)
    return record_version
