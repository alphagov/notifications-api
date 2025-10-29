import threading

_model_context = threading.local()


class ModelProxy:
    def __getattr__(self, name):
        if not hasattr(_model_context, "db_obj"):
            raise RuntimeError("Model context is not set. Import from 'app.models' or 'app.models.bulk' first.")
        return getattr(_model_context.db_obj, name)


proxied_db = ModelProxy()


def set_model_context(db_obj):
    _model_context.db_obj = db_obj


def clear_model_context():
    if hasattr(_model_context, "db_obj"):
        del _model_context.db_obj
