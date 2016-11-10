from flask.ext.redis import FlaskRedis


class RedisClient:
    active = False
    redis_store = FlaskRedis()

    def init_app(self, app):
        self.active = app.config.get('REDIS_ENABLED')

        if self.active:
            self.redis_store.init_app(app)

    def set(self, key, value):
        if self.active:
            self.redis_store.set(key, value)

    def get(self, key):
        if self.active:
            self.redis_store.get(key)
