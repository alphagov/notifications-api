import redis


class RedisClient:
    def init_app(self, app, *args, **kwargs):
        self.active = app.config.get('REDIS_ENABLED')
        self.redis = None

        if self.active:
            self.redis = redis.StrictRedis(
                app.config.get('REDIS_HOST'),
                app.config.get('REDIS_PORT')
            )

    def set(self, key, value):
        self.redis.set(key, value)

    def get(self, key):
        return self.redis.get(key)

    def incr(self, key):
        return self.redis.incr(key)
