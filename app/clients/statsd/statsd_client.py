from statsd import StatsClient


class StatsdClient(StatsClient):
    def init_app(self, app, *args, **kwargs):
        self.active = app.config.get('STATSD_ENABLED')
        self.namespace = app.config.get('NOTIFY_ENVIRONMENT') + ".notifications.api."

        if self.active:
            StatsClient.__init__(
                self,
                app.config.get('STATSD_HOST'),
                app.config.get('STATSD_PORT'),
                prefix=app.config.get('STATSD_PREFIX')
            )

    def format_stat_name(self, stat):
        return self.namespace + stat

    def incr(self, stat, count=1, rate=1):
        if self.active:
            super(StatsClient, self).incr(self.format_stat_name(stat), count, rate)

    def timing(self, stat, delta, rate=1):
        if self.active:
            super(StatsClient, self).timing(self.format_stat_name(stat), delta, rate)

    def timing_with_dates(self, stat, start, end, rate=1):
        if self.active:
            delta = (start - end).total_seconds()
            super(StatsClient, self).timing(stat, delta, rate)
