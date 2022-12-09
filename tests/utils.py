from contextlib import contextmanager

import flask_sqlalchemy


@contextmanager
def count_sqlalchemy_queries():
    """Returns a callable that counts the number of SQLAlchemy queries executed since creation"""
    before = len(flask_sqlalchemy.get_debug_queries())

    def get_query_count():
        after = len(flask_sqlalchemy.get_debug_queries())
        return after - before

    yield get_query_count
