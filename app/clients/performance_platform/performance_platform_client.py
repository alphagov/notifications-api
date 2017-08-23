import base64
import json

from flask import current_app
import requests


class PerformancePlatformClient:

    @property
    def active(self):
        return self._active

    def init_app(self, app):
        self._active = app.config.get('PERFORMANCE_PLATFORM_ENABLED')
        if self.active:
            self.performance_platform_url = app.config.get('PERFORMANCE_PLATFORM_URL')
            self.performance_platform_endpoints = app.config.get('PERFORMANCE_PLATFORM_ENDPOINTS')

    def send_stats_to_performance_platform(self, dataset, payload):
        if self.active:
            bearer_token = self.performance_platform_endpoints[dataset]
            headers = {
                'Content-Type': "application/json",
                'Authorization': 'Bearer {}'.format(bearer_token)
            }
            resp = requests.post(
                self.performance_platform_url + dataset,
                json=payload,
                headers=headers
            )

            if resp.status_code == 200:
                current_app.logger.info(
                    "Updated performance platform successfully with payload {}".format(json.dumps(payload))
                )
            else:
                current_app.logger.error(
                    "Performance platform update request failed for payload with response details: {} '{}'".format(
                        json.dumps(payload),
                        resp.status_code
                    )
                )
                resp.raise_for_status()

    @staticmethod
    def add_id_to_payload(payload):
        payload_string = '{}{}{}{}{}'.format(
            payload['_timestamp'],
            payload['service'],
            payload['channel'],
            payload['dataType'],
            payload['period']
        )
        _id = base64.b64encode(payload_string.encode('utf-8'))
        payload.update({'_id': _id.decode('utf-8')})
