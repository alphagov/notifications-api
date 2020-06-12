from cachetools import TTLCache


class ServiceIsActiveCache(object):
    def __init__(self):
        self.cache = TTLCache(maxsize=1024, ttl=30)

    def get(self, service_id):
        try:
            return self.cache[service_id]
        except KeyError:
            return None

    def put(self, s, active):
        self.cache[s] = active
