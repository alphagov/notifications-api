import datetime

from functools import wraps


def create_history(obj):
    history_mapper = obj.__history_mapper__
    history_model = history_mapper.class_
    history = history_model()
    if obj.version:
        obj.version += 1
    else:
        obj.version = 1
        obj.created_at = datetime.datetime.now()
    for prop in history_mapper.iterate_properties:
        if obj.__mapper__.get_property(prop.key):
            setattr(history, prop.key, getattr(obj, prop.key))
    history.created_by_id = obj.created_by.id
    return history


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
        import itertools
        from app import db
        from app.history_meta import versioned_objects
        from app.dao.dao_utils import create_history
        func(*args, **kwargs)
        for obj in versioned_objects(itertools.chain(db.session.new, db.session.dirty)):
            history = create_history(obj)
            db.session.add(history)
    return record_version
