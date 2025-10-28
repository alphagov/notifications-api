from flask_sqlalchemy.session import Session


class BindForcingSession(Session):
    def __init__(self, *args, bind_key=None, **kwargs):
        self.bind_key = bind_key
        super().__init__(*args, **kwargs)

    def get_bind(self, *args, bind=None, **kwargs):
        return self._db.engines[self.bind_key]
