from statsd import StatsClient


class StatsdClient(StatsClient):
    def init_app(self, app, *args, **kwargs):
        StatsClient.__init__(
            self,
            app.config.get('STATSD_HOST'),
            app.config.get('STATSD_PORT'),
            prefix=app.config.get('STATSD_PREFIX')
        )
        self.active = app.config.get('STATSD_ENABLED')

    def incr(self, stat, count=1, rate=1):
        if self.active:
            super(StatsClient, self).incr(stat, count, rate)

    def timing(self, stat, delta, rate=1):
        if self.active:
            super(StatsClient, self).timing(stat, delta, rate)


    def timing_with_dates(self, stat, start, end, rate=1):
        if self.active:
            delta = (start - end).total_seconds() * 1000
            super(StatsClient, self).timing(stat, delta, rate)