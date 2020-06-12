import operator
from threading import RLock

from cachetools import cachedmethod, TTLCache
from collections import namedtuple


Permission = namedtuple('Permission', ['permission'])


class PermissionsForServiceCache(object):
    def __init__(self):
        self.lock = RLock()
        self.cache = TTLCache(ttl=2, maxsize=1024)
        self.permissions_for_service = {}

    @cachedmethod(operator.attrgetter('cache'), lock=RLock)
    def get(self, service_id):
        with self.lock:
            try:
                return self.permissions_for_service[service_id]
            except KeyError:
                return None

    def put(self, s, ps):
        with self.lock:
            self.permissions_for_service[s] = [Permission(p.permission) for p in ps]
