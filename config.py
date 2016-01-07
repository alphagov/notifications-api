
class Config(object):
    DEBUG = False
    NOTIFY_LOG_LEVEL = 'DEBUG'
    NOTIFY_APP_NAME = 'api'
    NOTIFY_LOG_PATH = '/var/log/notify/application.log'


class Development(Config):
    DEBUG = True


class Test(Config):
    DEBUG = True


class Live(Config):
    pass

configs = {
    'development': Development,
    'test': Test,
    'live': Live,
}
