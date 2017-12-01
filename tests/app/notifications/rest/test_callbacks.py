import uuid

from datetime import datetime

from flask import json
from freezegun import freeze_time

import app.celery.tasks
from app.dao.notifications_dao import (
    get_notification_by_id
)
from tests.app.conftest import sample_notification as create_sample_notification


def firetext_post(client, data):
    return client.post(
        path='/notifications/sms/firetext',
        data=data,
        headers=[
            ('Content-Type', 'application/x-www-form-urlencoded'),
            ('X-Forwarded-For', '203.0.113.195, 70.41.3.18, 150.172.238.178') # fake IPs
        ])


def mmg_post(client, data):
    return client.post(
        path='/notifications/sms/mmg',
        data=data,
        headers=[
            ('Content-Type', 'application/json'),
            ('X-Forwarded-For', '203.0.113.195, 70.41.3.18, 150.172.238.178') # fake IPs
        ])


def dvla_post(client, data):
    return client.post(
        path='/notifications/letter/dvla',
        data=data,
        headers=[('Content-Type', 'application/json')]
    )


def test_dvla_callback_returns_400_with_invalid_request(client):
    data = json.dumps({"foo": "bar"})
    response = dvla_post(client, data)
    assert response.status_code == 400


def test_dvla_callback_autoconfirms_subscription(client, mocker):
    autoconfirm_mock = mocker.patch('app.notifications.notifications_letter_callback.autoconfirm_subscription')

    data = _sns_confirmation_callback()
    response = dvla_post(client, data)
    assert response.status_code == 200
    assert autoconfirm_mock.called


def test_dvla_callback_autoconfirm_does_not_call_update_letter_notifications_task(client, mocker):
    autoconfirm_mock = mocker.patch('app.notifications.notifications_letter_callback.autoconfirm_subscription')
    update_task = \
        mocker.patch('app.notifications.notifications_letter_callback.update_letter_notifications_statuses.apply_async')

    data = _sns_confirmation_callback()
    response = dvla_post(client, data)

    assert response.status_code == 200
    assert autoconfirm_mock.called
    assert not update_task.called


def test_dvla_callback_calls_update_letter_notifications_task(client, mocker):
    update_task = \
        mocker.patch('app.notifications.notifications_letter_callback.update_letter_notifications_statuses.apply_async')
    data = _sample_sns_s3_callback()
    response = dvla_post(client, data)

    assert response.status_code == 200
    assert update_task.called
    update_task.assert_called_with(['bar.txt'], queue='notify-internal-tasks')


def test_dvla_callback_does_not_raise_error_parsing_json_for_plaintext_header(client, mocker):
    mocker.patch('app.notifications.notifications_letter_callback.update_letter_notifications_statuses.apply_async')
    data = _sample_sns_s3_callback()
    response = dvla_post(client, data)

    assert response.status_code == 200


def test_firetext_callback_should_not_need_auth(client, mocker):
    mocker.patch('app.statsd_client.incr')
    data = 'mobile=441234123123&status=0&reference=send-sms-code&time=2016-03-10 14:17:00'

    response = firetext_post(client, data)
    assert response.status_code == 200


def test_firetext_callback_should_return_400_if_empty_reference(client, mocker):
    mocker.patch('app.statsd_client.incr')
    data = 'mobile=441234123123&status=0&reference=&time=2016-03-10 14:17:00'
    response = firetext_post(client, data)

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == ['Firetext callback failed: reference missing']


def test_firetext_callback_should_return_400_if_no_reference(client, mocker):
    mocker.patch('app.statsd_client.incr')
    data = 'mobile=441234123123&status=0&time=2016-03-10 14:17:00'
    response = firetext_post(client, data)
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == ['Firetext callback failed: reference missing']


def test_firetext_callback_should_return_200_if_send_sms_reference(client, mocker):
    mocker.patch('app.statsd_client.incr')
    data = 'mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=send-sms-code'
    response = firetext_post(client, data)
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_resp['result'] == 'success'
    assert json_resp['message'] == 'Firetext callback succeeded: send-sms-code'


def test_firetext_callback_should_return_400_if_no_status(client, mocker):
    mocker.patch('app.statsd_client.incr')
    data = 'mobile=441234123123&time=2016-03-10 14:17:00&reference=send-sms-code'
    response = firetext_post(client, data)
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == ['Firetext callback failed: status missing']


def test_firetext_callback_should_return_400_if_unknown_status(client, mocker):
    mocker.patch('app.statsd_client.incr')
    data = 'mobile=441234123123&status=99&time=2016-03-10 14:17:00&reference={}'.format(uuid.uuid4())
    response = firetext_post(client, data)

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'Firetext callback failed: status 99 not found.'


def test_firetext_callback_returns_200_when_notification_id_not_found_or_already_updated(client, mocker):
    mocker.patch('app.statsd_client.incr')
    data = 'mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=1234'
    response = firetext_post(client, data)
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'Firetext callback with invalid reference 1234'


def test_callback_should_return_200_if_cannot_find_notification_id(
    notify_db,
    notify_db_session,
    client,
    mocker
):
    mocker.patch('app.statsd_client.incr')
    missing_notification_id = uuid.uuid4()
    data = 'mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
        missing_notification_id)
    response = firetext_post(client, data)

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_resp['result'] == 'success'


def test_firetext_callback_should_update_notification_status(
        notify_db, notify_db_session, client, sample_email_template, mocker
):
    mocker.patch('app.statsd_client.incr')
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        reference='ref',
        status='sending',
        sent_at=datetime.utcnow())

    original = get_notification_by_id(notification.id)
    assert original.status == 'sending'
    data = 'mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
        notification.id)
    response = firetext_post(client, data)

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_resp['result'] == 'success'
    assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
        notification.id
    )
    updated = get_notification_by_id(notification.id)
    assert updated.status == 'delivered'
    assert get_notification_by_id(notification.id).status == 'delivered'
    assert send_mock.called_once_with([notification.id], queue="notify-internal-tasks")


def test_firetext_callback_should_update_notification_status_failed(
        notify_db, notify_db_session, client, sample_template, mocker
):
    mocker.patch('app.statsd_client.incr')
    mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        reference='ref',
        status='sending',
        sent_at=datetime.utcnow())

    original = get_notification_by_id(notification.id)
    assert original.status == 'sending'

    data = 'mobile=441234123123&status=1&time=2016-03-10 14:17:00&reference={}'.format(
        notification.id)
    response = firetext_post(client, data)

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_resp['result'] == 'success'
    assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
        notification.id
    )
    assert get_notification_by_id(notification.id).status == 'permanent-failure'


def test_firetext_callback_should_update_notification_status_pending(client, notify_db, notify_db_session, mocker):
    mocker.patch('app.statsd_client.incr')
    mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
    )
    original = get_notification_by_id(notification.id)
    assert original.status == 'sending'
    data = 'mobile=441234123123&status=2&time=2016-03-10 14:17:00&reference={}'.format(
        notification.id)
    response = firetext_post(client, data)

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_resp['result'] == 'success'
    assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
        notification.id
    )
    assert get_notification_by_id(notification.id).status == 'pending'


def test_process_mmg_response_return_200_when_cid_is_send_sms_code(client):
    data = '{"reference": "10100164", "CID": "send-sms-code", "MSISDN": "447775349060", "status": "3", \
        "deliverytime": "2016-04-05 16:01:07"}'

    response = mmg_post(client, data)
    assert response.status_code == 200
    json_data = json.loads(response.data)
    assert json_data['result'] == 'success'
    assert json_data['message'] == 'MMG callback succeeded: send-sms-code'


def test_process_mmg_response_returns_200_when_cid_is_valid_notification_id(
        notify_db, notify_db_session, client, mocker
):
    mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
    )
    data = json.dumps({"reference": "mmg_reference",
                       "CID": str(notification.id),
                       "MSISDN": "447777349060",
                       "status": "3",
                       "deliverytime": "2016-04-05 16:01:07"})

    response = mmg_post(client, data)

    assert response.status_code == 200
    json_data = json.loads(response.data)
    assert json_data['result'] == 'success'
    assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
    assert get_notification_by_id(notification.id).status == 'delivered'


def test_process_mmg_response_status_5_updates_notification_with_permanently_failed(
    notify_db, notify_db_session, client, mocker
):
    mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
    )

    data = json.dumps({"reference": "mmg_reference",
                       "CID": str(notification.id),
                       "MSISDN": "447777349060",
                       "status": 5})

    response = mmg_post(client, data)
    assert response.status_code == 200
    json_data = json.loads(response.data)
    assert json_data['result'] == 'success'
    assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
    assert get_notification_by_id(notification.id).status == 'permanent-failure'


def test_process_mmg_response_status_2_updates_notification_with_permanently_failed(
    notify_db, notify_db_session, client, mocker
):
    mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
    )
    data = json.dumps({"reference": "mmg_reference",
                       "CID": str(notification.id),
                       "MSISDN": "447777349060",
                       "status": 2})

    response = mmg_post(client, data)
    assert response.status_code == 200
    json_data = json.loads(response.data)
    assert json_data['result'] == 'success'
    assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
    assert get_notification_by_id(notification.id).status == 'permanent-failure'


def test_process_mmg_response_status_4_updates_notification_with_temporary_failed(
        notify_db, notify_db_session, client, mocker
):
    mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
    )

    data = json.dumps({"reference": "mmg_reference",
                       "CID": str(notification.id),
                       "MSISDN": "447777349060",
                       "status": 4})

    response = mmg_post(client, data)
    assert response.status_code == 200
    json_data = json.loads(response.data)
    assert json_data['result'] == 'success'
    assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
    assert get_notification_by_id(notification.id).status == 'temporary-failure'


def test_process_mmg_response_unknown_status_updates_notification_with_failed(
        notify_db, notify_db_session, client, mocker
):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
    )
    data = json.dumps({"reference": "mmg_reference",
                       "CID": str(notification.id),
                       "MSISDN": "447777349060",
                       "status": 10})

    response = mmg_post(client, data)
    assert response.status_code == 200
    json_data = json.loads(response.data)
    assert json_data['result'] == 'success'
    assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(notification.id)
    assert get_notification_by_id(notification.id).status == 'failed'


def test_process_mmg_response_returns_400_for_malformed_data(client):
    data = json.dumps({"reference": "mmg_reference",
                       "monkey": 'random thing',
                       "MSISDN": "447777349060",
                       "no_status": 00,
                       "deliverytime": "2016-04-05 16:01:07"})

    response = mmg_post(client, data)
    assert response.status_code == 400
    json_data = json.loads(response.data)
    assert json_data['result'] == 'error'
    assert len(json_data['message']) == 2
    assert "{} callback failed: {} missing".format('MMG', 'status') in json_data['message']
    assert "{} callback failed: {} missing".format('MMG', 'CID') in json_data['message']


def test_mmg_callback_returns_200_when_notification_id_not_found_or_already_updated(client):
    data = '{"reference": "10100164", "CID": "send-sms-code", "MSISDN": "447775349060", "status": "3", \
             "deliverytime": "2016-04-05 16:01:07"}'

    response = mmg_post(client, data)
    assert response.status_code == 200


def test_process_mmg_response_records_statsd(notify_db, notify_db_session, client, mocker):
    with freeze_time('2001-01-01T12:00:00'):

        mocker.patch('app.statsd_client.incr')
        mocker.patch('app.statsd_client.timing_with_dates')
        mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
        )
        notification = create_sample_notification(
            notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
        )

        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(notification.id),
                           "MSISDN": "447777349060",
                           "status": "3",
                           "deliverytime": "2016-04-05 16:01:07"})

        mmg_post(client, data)

        app.statsd_client.incr.assert_any_call("callback.mmg.delivered")
        app.statsd_client.timing_with_dates.assert_any_call(
            "callback.mmg.elapsed-time", datetime.utcnow(), notification.sent_at
        )


def test_firetext_callback_should_record_statsd(client, notify_db, notify_db_session, mocker):
    with freeze_time('2001-01-01T12:00:00'):

        mocker.patch('app.statsd_client.incr')
        mocker.patch('app.statsd_client.timing_with_dates')
        mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
        )
        notification = create_sample_notification(
            notify_db, notify_db_session, status='sending', sent_at=datetime.utcnow()
        )

        data = 'mobile=441234123123&status=0&time=2016-03-10 14:17:00&code=101&reference={}'.format(
            notification.id)
        firetext_post(client, data)

        app.statsd_client.timing_with_dates.assert_any_call(
            "callback.firetext.elapsed-time", datetime.utcnow(), notification.sent_at
        )
        app.statsd_client.incr.assert_any_call("callback.firetext.delivered")


def _sample_sns_s3_callback():
    return json.dumps({
        "SigningCertURL": "foo.pem",
        "UnsubscribeURL": "bar",
        "Signature": "some-signature",
        "Type": "Notification",
        "Timestamp": "2016-05-03T08:35:12.884Z",
        "SignatureVersion": "1",
        "MessageId": "6adbfe0a-d610-509a-9c47-af894e90d32d",
        "Subject": "Amazon S3 Notification",
        "TopicArn": "sample-topic-arn",
        "Message": '{"Records":[{"eventVersion":"2.0","eventSource":"aws:s3","awsRegion":"eu-west-1","eventTime":"2017-05-16T11:38:41.073Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"some-p-id"},"requestParameters":{"sourceIPAddress":"8.8.8.8"},"responseElements":{"x-amz-request-id":"some-r-id","x-amz-id-2":"some-x-am-id"},"s3":{"s3SchemaVersion":"1.0","configurationId":"some-c-id","bucket":{"name":"some-bucket","ownerIdentity":{"principalId":"some-p-id"},"arn":"some-bucket-arn"},"object":{"key":"bar.txt","size":200,"eTag":"some-e-tag","versionId":"some-v-id","sequencer":"some-seq"}}}]}'  # noqa
    })


def _sns_confirmation_callback():
    return b'{\n    "Type": "SubscriptionConfirmation",\n    "MessageId": "165545c9-2a5c-472c-8df2-7ff2be2b3b1b",\n    "Token": "2336412f37fb687f5d51e6e241d09c805a5a57b30d712f794cc5f6a988666d92768dd60a747ba6f3beb71854e285d6ad02428b09ceece29417f1f02d609c582afbacc99c583a916b9981dd2728f4ae6fdb82efd087cc3b7849e05798d2d2785c03b0879594eeac82c01f235d0e717736",\n    "TopicArn": "arn:aws:sns:us-west-2:123456789012:MyTopic",\n    "Message": "You have chosen to subscribe to the topic arn:aws:sns:us-west-2:123456789012:MyTopic.\\nTo confirm the subscription, visit the SubscribeURL included in this message.",\n    "SubscribeURL": "https://sns.us-west-2.amazonaws.com/?Action=ConfirmSubscription&TopicArn=arn:aws:sns:us-west-2:123456789012:MyTopic&Token=2336412f37fb687f5d51e6e241d09c805a5a57b30d712f794cc5f6a988666d92768dd60a747ba6f3beb71854e285d6ad02428b09ceece29417f1f02d609c582afbacc99c583a916b9981dd2728f4ae6fdb82efd087cc3b7849e05798d2d2785c03b0879594eeac82c01f235d0e717736",\n    "Timestamp": "2012-04-26T20:45:04.751Z",\n    "SignatureVersion": "1",\n    "Signature": "EXAMPLEpH+DcEwjAPg8O9mY8dReBSwksfg2S7WKQcikcNKWLQjwu6A4VbeS0QHVCkhRS7fUQvi2egU3N858fiTDN6bkkOxYDVrY0Ad8L10Hs3zH81mtnPk5uvvolIC1CXGu43obcgFxeL3khZl8IKvO61GWB6jI9b5+gLPoBc1Q=",\n    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/SimpleNotificationService-f3ecfb7224c7233fe7bb5f59f96de52f.pem"\n}'  # noqa
