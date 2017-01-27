import base64
import json
from requests import request

from flask import current_app


class PerformancePlatformClient:

    def init_app(self, app):
        self.active = app.config.get('PERFORMANCE_PLATFORM_ENABLED')
        if self.active:
            self.bearer_token = app.config.get('PERFORMANCE_PLATFORM_TOKEN')
            self.performance_platform_url = current_app.config.get('PERFORMANCE_PLATFORM_URL')

    def send_performance_stats(self, date, channel, count, period):
        if self.active:
            payload = {
                '_timestamp': date,
                'service': 'govuk-notify',
                'channel': channel,
                'count': count,
                'dataType': 'notifications',
                'period': period
            }
            self._add_id_for_payload(payload)
            self._send_stats_to_performance_platform(payload)

    def _send_stats_to_performance_platform(self, payload):
        headers = {
            'Content-Type': "application/json",
            'Authorization': 'Bearer {}'.format(self.bearer_token)
        }
        resp = request(
            "POST",
            self.performance_platform_url,
            data=json.dumps(payload),
            headers=headers
        )

        if resp.status_code != 200:
            current_app.logger.error(
                "Performance platform update request failed with {} '{}'".format(
                    resp.status_code,
                    resp.json())
            )

    def _add_id_for_payload(self, payload):
        payload_string = '{}{}{}{}{}'.format(
            payload['_timestamp'],
            payload['service'],
            payload['channel'],
            payload['dataType'],
            payload['period']
        )
        _id = base64.b64encode(payload_string.encode('utf-8'))
        payload.update({'_id': _id.decode('utf-8')})
