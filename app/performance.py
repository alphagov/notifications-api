import os


def init_performance_monitoring():
    environment = os.getenv("NOTIFY_ENVIRONMENT").lower()
    enable_apm = environment in {"development", "preview", "staging"}

    if enable_apm:
        if os.getenv("NEW_RELIC_ENABLED") == "1":
            import newrelic.agent

            # Expects NEW_RELIC_LICENSE_KEY set in environment as well.
            newrelic.agent.initialize("newrelic.ini", environment=environment, ignore_errors=False)
