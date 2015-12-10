
class Config(object):
    DEBUG = False


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
