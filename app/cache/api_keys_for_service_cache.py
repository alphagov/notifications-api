from cachetools import TTLCache
from collections import namedtuple


ApiKey = namedtuple('ApiKey', ['id', 'secret', 'expiry_date'])


class ApiKeysForServiceCache(object):
    def __init__(self):
        self.cache = TTLCache(maxsize=1024, ttl=10)

    def get(self, service_id):
        try:
            return self.cache[service_id]
        except KeyError:
            return None

    def put(self, s, ks):
        self.cache[s] = [ApiKey(k.id, k.secret, k.expiry_date) for k in ks]
