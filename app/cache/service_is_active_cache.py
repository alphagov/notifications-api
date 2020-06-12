import operator
from threading import RLock

from cachetools import cachedmethod, TTLCache


class ServiceIsActiveCache(object):
    def __init__(self):
        self.lock = RLock()
        self.cache = TTLCache(ttl=2, maxsize=1024)
        self.active_services = {}

    def get(self, service_id):
        with self.lock:
            try:
                return self.active_services[service_id]
            except KeyError:
                return None

    def put(self, s, active):
        with self.lock:
            self.active_services[s] = active
