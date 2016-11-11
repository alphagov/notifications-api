from datetime import datetime


def cache_key(service_id):
    return "{}-{}-{}".format(str(service_id), datetime.utcnow().strftime("%Y-%m-%d"), "count")
