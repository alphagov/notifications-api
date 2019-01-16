import requests
from functools import wraps
from flask import current_app


def cronitor(task_name):
    # check if task_name is in config
    def decorator(func):
        def ping_cronitor(command):
            if not current_app.config['CRONITOR_ENABLED']:
                return

            task_slug = current_app.config['CRONITOR_KEYS'].get(task_name)
            if not task_slug:
                current_app.logger.error(
                    'Cronitor enabled but task_name {} not found in environment'.format(task_name)
                )

            if command not in {'run', 'complete', 'fail'}:
                raise ValueError('command {} not a valid cronitor command'.format(command))

            resp = requests.get(
                'https://cronitor.link/{}/{}'.format(task_slug, command),
                # cronitor limits msg to 1000 characters
                params={
                    'host': current_app.config['API_HOST_NAME'],
                }
            )
            if resp.status_code != 200:
                current_app.logger.warning('Cronitor API returned {} for task {}, body {}'.format(
                    resp.status_code,
                    task_name,
                    resp.text
                ))

        @wraps(func)
        def inner_decorator(*args, **kwargs):
            ping_cronitor('run')
            try:
                ret = func(*args, **kwargs)
                status = 'complete'
                return ret
            except Exception:
                status = 'fail'
                raise
            finally:
                ping_cronitor(status)

        return inner_decorator
    return decorator
