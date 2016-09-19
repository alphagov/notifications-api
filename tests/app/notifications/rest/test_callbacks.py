import uuid

from datetime import datetime
from flask import json
from freezegun import freeze_time

import app.celery.tasks
from app.dao.notifications_dao import (
    get_notification_by_id
)
from app.models import NotificationStatistics
from tests.app.conftest import sample_notification as create_sample_notification


def test_firetext_callback_should_not_need_auth(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&reference=send-sms-code&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            assert response.status_code == 200


def test_firetext_callback_should_return_400_if_empty_reference(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&reference=&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: reference missing']


def test_firetext_callback_should_return_400_if_no_reference(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: reference missing']


def test_firetext_callback_should_return_200_if_send_sms_reference(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=send-sms-code',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded: send-sms-code'


def test_firetext_callback_should_return_400_if_no_status(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&time=2016-03-10 14:17:00&reference=send-sms-code',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: status missing']


def test_firetext_callback_should_return_400_if_unknown_status(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=99&time=2016-03-10 14:17:00&reference={}'.format(uuid.uuid4()),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback failed: status 99 not found.'


def test_firetext_callback_should_return_400_if_invalid_guid_notification_id(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=1234',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback with invalid reference 1234'


def test_firetext_callback_should_return_404_if_cannot_find_notification_id(
    notify_db,
    notify_db_session,
    notify_api,
    mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            missing_notification_id = uuid.uuid4()
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    missing_notification_id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback failed: notification {} either not found ' \
                                           'or already updated from sending. Status {}'.format(
                missing_notification_id,
                'Delivered'
            )


def test_firetext_callback_should_update_notification_status(
        notify_db, notify_db_session, notify_api, sample_email_template, mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')

            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='sending',
                sent_at=datetime.utcnow())

            original = get_notification_by_id(notification.id)
            assert original.status == 'sending'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                notification.id
            )
            updated = get_notification_by_id(notification.id)
            assert updated.status == 'delivered'
            assert get_notification_by_id(notification.id).status == 'delivered'


def test_firetext_callback_should_update_notification_status_failed(
        notify_db, notify_db_session, notify_api, sample_template, mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')

            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_template,
                reference='ref',
                status='sending',
                sent_at=datetime.utcnow())

            original = get_notification_by_id(notification.id)
            assert original.status == 'sending'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=1&time=2016-03-10 14:17:00&reference={}'.format(
                    notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                notification.id
            )
            assert get_notification_by_id(notification.id).status == 'permanent-failure'


def test_firetext_callback_should_update_notification_status_pending(notify_api, notify_db, notify_db_session, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            notification = create_sample_notification(
                notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
            )
            original = get_notification_by_id(notification.id)
            assert original.status == 'sending'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=2&time=2016-03-10 14:17:00&reference={}'.format(
                    notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                notification.id
            )
            assert get_notification_by_id(notification.id).status == 'pending'


def test_firetext_callback_should_update_multiple_notification_status_sent(
    notify_api,
    notify_db,
    notify_db_session,
    mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            notification1 = create_sample_notification(
                notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
            )
            notification2 = create_sample_notification(
                notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
            )
            notification3 = create_sample_notification(
                notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
            )

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification1.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification2.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification3.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])


def test_process_mmg_response_return_200_when_cid_is_send_sms_code(notify_api):
    with notify_api.test_request_context():
        data = '{"reference": "10100164", "CID": "send-sms-code", "MSISDN": "447775349060", "status": "3", \
        "deliverytime": "2016-04-05 16:01:07"}'

        with notify_api.test_client() as client:
            response = client.post(path='notifications/sms/mmg',
                                   data=data,
                                   headers=[('Content-Type', 'application/json')])
            assert response.status_code == 200
            json_data = json.loads(response.data)
            assert json_data['result'] == 'success'
            assert json_data['message'] == 'MMG callback succeeded: send-sms-code'


def test_process_mmg_response_returns_200_when_cid_is_valid_notification_id(
        notify_db, notify_db_session, notify_api
):
    with notify_api.test_client() as client:
        notification = create_sample_notification(
            notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
        )
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(notification.id),
                           "MSISDN": "447777349060",
                           "status": "3",
                           "deliverytime": "2016-04-05 16:01:07"})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
        assert get_notification_by_id(notification.id).status == 'delivered'


def test_process_mmg_response_status_5_updates_notification_with_permanently_failed(
    notify_db, notify_db_session, notify_api
):
    with notify_api.test_client() as client:
        notification = create_sample_notification(
            notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
        )

        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(notification.id),
                           "MSISDN": "447777349060",
                           "status": 5})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
        assert get_notification_by_id(notification.id).status == 'permanent-failure'


def test_process_mmg_response_status_2_updates_notification_with_permanently_failed(
    notify_db, notify_db_session, notify_api
):
    with notify_api.test_client() as client:
        notification = create_sample_notification(
            notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
        )
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(notification.id),
                           "MSISDN": "447777349060",
                           "status": 2})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
        assert get_notification_by_id(notification.id).status == 'permanent-failure'


def test_process_mmg_response_status_4_updates_notification_with_temporary_failed(
        notify_db, notify_db_session, notify_api
):
    with notify_api.test_client() as client:
        notification = create_sample_notification(
            notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
        )

        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(notification.id),
                           "MSISDN": "447777349060",
                           "status": 4})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
        assert get_notification_by_id(notification.id).status == 'temporary-failure'


def test_process_mmg_response_unknown_status_updates_notification_with_failed(
        notify_db, notify_db_session, notify_api
):
    with notify_api.test_client() as client:

        notification = create_sample_notification(
            notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
        )
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(notification.id),
                           "MSISDN": "447777349060",
                           "status": 10})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
        assert get_notification_by_id(notification.id).status == 'failed'


def test_process_mmg_response_returns_400_for_malformed_data(notify_api):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "monkey": 'random thing',
                           "MSISDN": "447777349060",
                           "no_status": 00,
                           "deliverytime": "2016-04-05 16:01:07"})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 400
        json_data = json.loads(response.data)
        assert json_data['result'] == 'error'
        assert len(json_data['message']) == 2
        assert "{} callback failed: {} missing".format('MMG', 'status') in json_data['message']
        assert "{} callback failed: {} missing".format('MMG', 'CID') in json_data['message']


def test_ses_callback_should_not_need_auth(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            assert response.status_code == 404


def test_ses_callback_should_fail_if_invalid_json(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data="nonsense",
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: invalid json'


def test_ses_callback_should_fail_if_invalid_notification_type(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_invalid_notification_type_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: status Unknown not found'


def test_ses_callback_should_fail_if_missing_message_id(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_missing_notification_id_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: messageId missing'


def test_ses_callback_should_fail_if_notification_cannot_be_found(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_invalid_notification_id_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: notification either not found or already updated from sending. Status delivered'  # noqa


def test_ses_callback_should_update_notification_status(
        notify_api,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            with freeze_time('2001-01-01T12:00:00'):
                mocker.patch('app.statsd_client.incr')
                mocker.patch('app.statsd_client.timing_with_dates')
                notification = create_sample_notification(
                    notify_db,
                    notify_db_session,
                    template=sample_email_template,
                    reference='ref',
                    status='sending',
                    sent_at=datetime.utcnow()
                )

                assert get_notification_by_id(notification.id).status == 'sending'

                response = client.post(
                    path='/notifications/email/ses',
                    data=ses_notification_callback(),
                    headers=[('Content-Type', 'text/plain; charset=UTF-8')]
                )
                json_resp = json.loads(response.get_data(as_text=True))
                assert response.status_code == 200
                assert json_resp['result'] == 'success'
                assert json_resp['message'] == 'SES callback succeeded'
                assert get_notification_by_id(notification.id).status == 'delivered'
                app.statsd_client.timing_with_dates.assert_any_call(
                    "callback.ses.elapsed-time", datetime.utcnow(), notification.sent_at
                )
                app.statsd_client.incr.assert_any_call("callback.ses.delivered")


def test_ses_callback_should_update_multiple_notification_status_sent(
        notify_api,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification1 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref1',
                sent_at=datetime.utcnow(),
                status='sending')

            notification2 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref2',
                sent_at=datetime.utcnow(),
                status='sending')

            notification3 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref3',
                sent_at=datetime.utcnow(),
                status='sending')

            resp1 = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(ref='ref1'),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            resp2 = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(ref='ref2'),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            resp3 = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(ref='ref3'),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )

            assert resp1.status_code == 200
            assert resp2.status_code == 200
            assert resp3.status_code == 200


def test_ses_callback_should_set_status_to_temporary_failure(notify_api,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='sending',
                sent_at=datetime.utcnow()
            )
            assert get_notification_by_id(notification.id).status == 'sending'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_soft_bounce_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'
            assert get_notification_by_id(notification.id).status == 'temporary-failure'


def test_ses_callback_should_not_set_status_once_status_is_delivered(notify_api,
                                                                     notify_db,
                                                                     notify_db_session,
                                                                     sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='delivered',
                sent_at=datetime.utcnow()
            )

            assert get_notification_by_id(notification.id).status == 'delivered'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_soft_bounce_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: notification either not found or already updated from sending. Status temporary-failure'  # noqa
            assert get_notification_by_id(notification.id).status == 'delivered'


def test_ses_callback_should_set_status_to_permanent_failure(notify_api,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref',
                status='sending',
                sent_at=datetime.utcnow()
            )

            assert get_notification_by_id(notification.id).status == 'sending'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_hard_bounce_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'
            assert get_notification_by_id(notification.id).status == 'permanent-failure'


def test_process_mmg_response_records_statsd(notify_db, notify_db_session, notify_api, mocker):
    with notify_api.test_client() as client:
        with freeze_time('2001-01-01T12:00:00'):

            mocker.patch('app.statsd_client.incr')
            mocker.patch('app.statsd_client.timing_with_dates')
            notification = create_sample_notification(
                notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
            )

            data = json.dumps({"reference": "mmg_reference",
                               "CID": str(notification.id),
                               "MSISDN": "447777349060",
                               "status": "3",
                               "deliverytime": "2016-04-05 16:01:07"})

            client.post(path='notifications/sms/mmg',
                        data=data,
                        headers=[('Content-Type', 'application/json')])

            app.statsd_client.incr.assert_any_call("callback.mmg.delivered")
            app.statsd_client.timing_with_dates.assert_any_call(
                "callback.mmg.elapsed-time", datetime.utcnow(), notification.sent_at
            )


def test_firetext_callback_should_record_statsd(notify_api, notify_db, notify_db_session, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            with freeze_time('2001-01-01T12:00:00'):

                mocker.patch('app.statsd_client.incr')
                mocker.patch('app.statsd_client.timing_with_dates')
                notification = create_sample_notification(
                    notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
                )

                client.post(
                    path='/notifications/sms/firetext',
                    data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&code=101&reference={}'.format(
                        notification.id
                    ),
                    headers=[('Content-Type', 'application/x-www-form-urlencoded')])

                app.statsd_client.timing_with_dates.assert_any_call(
                    "callback.firetext.elapsed-time", datetime.utcnow(), notification.sent_at
                )
                app.statsd_client.incr.assert_any_call("callback.firetext.delivered")


def ses_notification_callback(ref='ref'):
    return str.encode(
        '{\n  "Type" : "Notification",\n  "MessageId" : "%(ref)s",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"%(ref)s\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}' % {'ref': ref}  # noqa
    )


def ses_invalid_notification_id_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "missing",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"missing\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_missing_notification_id_callback():
    return b'{\n  "Type" : "Notification",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_invalid_notification_type_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Unknown\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_hard_bounce_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Bounce\\",\\"bounce\\":{\\"bounceType\\":\\"Permanent\\",\\"bounceSubType\\":\\"General\\"}, \\"mail\\":{\\"messageId\\":\\"ref\\",\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_soft_bounce_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Bounce\\",\\"bounce\\":{\\"bounceType\\":\\"Undetermined\\",\\"bounceSubType\\":\\"General\\"}, \\"mail\\":{\\"messageId\\":\\"ref\\",\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def get_notification_stats(service_id):
    return NotificationStatistics.query.filter_by(service_id=service_id).one()
