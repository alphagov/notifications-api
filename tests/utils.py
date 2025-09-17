import flask_sqlalchemy


class QueryRecorder:
    def __init__(self):
        self.queries = []
        self._count_on_enter = None

    def __enter__(self):
        self._count_on_enter = len(flask_sqlalchemy.get_debug_queries())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.queries = flask_sqlalchemy.get_debug_queries()[self._count_on_enter :]
