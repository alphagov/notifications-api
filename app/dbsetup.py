from flask_sqlalchemy.session import Session


class RoutingSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bind_key_name = None

    def using_bind(self, bind_key):
        self.bind_key_name = bind_key
        return self  # Return self to allow chaining .query()

    def get_bind(self, *args, **kwargs):
        if self.bind_key_name:
            bind = self._db.get_engine(bind=self.bind_key_name)
            self.bind_key_name = None
            return bind

        # If no custom bind was set, use the default
        return super().get_bind(*args, **kwargs)
