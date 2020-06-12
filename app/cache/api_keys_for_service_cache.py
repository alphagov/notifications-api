import operator
from threading import RLock

from cachetools import cachedmethod, TTLCache
from collections import namedtuple


ApiKey = namedtuple('ApiKey', ['id', 'secret', 'expiry_date'])


class ApiKeysForServiceCache(object):
    def __init__(self):
        self.lock = RLock()
        self.cache = TTLCache(ttl=10, maxsize=1024)
        self.api_keys_for_service = {}

    @cachedmethod(operator.attrgetter('cache'), lock=RLock)
    def get(self, service_id):
        with self.lock:
            try:
                return self.api_keys_for_service[service_id]
            except KeyError:
                return None

    def put(self, s, ks):
        with self.lock:
            self.api_keys_for_service[s] = [ApiKey(k.id, k.secret, k.expiry_date) for k in ks]
