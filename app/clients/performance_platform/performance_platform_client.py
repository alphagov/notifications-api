import base64
import json

from flask import current_app
import requests

from notifications_utils.timezones import convert_utc_to_bst


class PerformancePlatformClient:

    @property
    def active(self):
        return self._active

    def init_app(self, app):
        self._active = app.config.get('PERFORMANCE_PLATFORM_ENABLED')
        if self.active:
            self.performance_platform_url = app.config.get('PERFORMANCE_PLATFORM_URL')
            self.performance_platform_endpoints = app.config.get('PERFORMANCE_PLATFORM_ENDPOINTS')

    def send_stats_to_performance_platform(self, payload):
        if self.active:
            bearer_token = self.performance_platform_endpoints[payload['dataType']]
            headers = {
                'Content-Type': "application/json",
                'Authorization': 'Bearer {}'.format(bearer_token)
            }
            resp = requests.post(
                self.performance_platform_url + payload['dataType'],
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
    def format_payload(*, dataset, date, group_name, group_value, count, period='day'):
        """
        :param dataset - the name of the overall graph, as referred to in the endpoint.
        :param date - the date we're sending stats for
        :param group_name - the name of the individual groups of data, eg "channel" or "status"
        :param group_value - the value of the group, eg "sms" or "email" for group_name=channel
        :param count - the actual numeric value to send
        :param period - the period that this data covers - "day", "week", "month", "quarter".
        """
        payload = {
            '_timestamp': convert_utc_to_bst(date).isoformat(),
            'service': 'govuk-notify',
            'dataType': dataset,
            'period': period,
            'count': count,
            group_name: group_value,
        }
        payload['_id'] = PerformancePlatformClient.generate_payload_id(payload, group_name)
        return payload

    @staticmethod
    def generate_payload_id(payload, group_name):
        """
        group_name is the name of the group - eg "channel" or "status"
        """
        payload_string = '{}{}{}{}{}'.format(
            payload['_timestamp'],
            payload['service'],
            payload[group_name],
            payload['dataType'],
            payload['period']
        )
        _id = base64.b64encode(payload_string.encode('utf-8'))
        return _id.decode('utf-8')
