from flask.ext.redis import FlaskRedis
from flask import current_app


class RedisClient:
    redis_store = FlaskRedis()
    active = False

    def init_app(self, app):
        self.active = app.config.get('REDIS_ENABLED')

        if self.active:
            self.redis_store.init_app(app)

    def set(self, key, value, ex=None, px=None, nx=False, xx=False, raise_exception=False):
        if self.active:
            try:
                self.redis_store.set(key, value, ex, px, nx, xx)
            except Exception as e:
                current_app.logger.exception(e)
                if raise_exception:
                    raise e

    def inc(self, key, raise_exception=False):
        if self.active:
            try:
                return self.redis_store.inc(key)
            except Exception as e:
                current_app.logger.exception(e)
                if raise_exception:
                    raise e

    def get(self, key, raise_exception=False):
        if self.active:
            try:
                return self.redis_store.get(key)
            except Exception as e:
                current_app.logger.exception(e)
                if raise_exception:
                    raise e
        return None
