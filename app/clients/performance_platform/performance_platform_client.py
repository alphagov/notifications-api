import base64
import json
from datetime import datetime

import requests
from flask import current_app

from app.utils import get_midnight_for_day_before, get_london_midnight_in_utc, convert_utc_time_in_bst


class PerformancePlatformClient:

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, value):
        self._active = value

    def init_app(self, app):
        self._active = app.config.get('PERFORMANCE_PLATFORM_ENABLED')
        if self.active:
            self.bearer_token = app.config.get('PERFORMANCE_PLATFORM_TOKEN')
            self.performance_platform_url = app.config.get('PERFORMANCE_PLATFORM_URL')

    def send_performance_stats(self, date, channel, count, period):
        if self.active:
            payload = {
                '_timestamp': convert_utc_time_in_bst(date).isoformat(),
                'service': 'govuk-notify',
                'channel': channel,
                'count': count,
                'dataType': 'notifications',
                'period': period
            }
            self._add_id_for_payload(payload)
            self._send_stats_to_performance_platform(payload)

    def get_total_sent_notifications_yesterday(self):
        today = datetime.utcnow()
        start_date = get_midnight_for_day_before(today)
        end_date = get_london_midnight_in_utc(today)

        from app.dao.notifications_dao import get_total_sent_notifications_in_date_range
        email_count = get_total_sent_notifications_in_date_range(start_date, end_date, 'email')
        sms_count = get_total_sent_notifications_in_date_range(start_date, end_date, 'sms')

        return {
            "start_date": start_date,
            "email": {
                "count": email_count
            },
            "sms": {
                "count": sms_count
            }
        }

    def _send_stats_to_performance_platform(self, payload):
        headers = {
            'Content-Type': "application/json",
            'Authorization': 'Bearer {}'.format(self.bearer_token)
        }
        resp = requests.post(
            self.performance_platform_url,
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
