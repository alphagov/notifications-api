from cachetools import TTLCache
from collections import namedtuple


Permission = namedtuple('Permission', ['permission'])


class PermissionsForServiceCache(object):
    def __init__(self):
        self.cache = TTLCache(maxsize=1024, ttl=2)

    def get(self, service_id):
        try:
            return self.cache[service_id]
        except KeyError:
            return None

    def put(self, s, ps):
        self.cache[s] = [Permission(p.permission) for p in ps]
