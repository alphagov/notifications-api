from datetime import datetime
from unittest.mock import call

from flask import json
from freezegun import freeze_time
from requests import HTTPError
import pytest

from app import statsd_client
from app.dao.notifications_dao import get_notification_by_id
from tests.app.conftest import sample_notification as create_sample_notification


def test_ses_callback_should_not_need_auth(client):
    response = client.post(
        path='/notifications/email/ses',
        data=ses_notification_callback(),
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    assert response.status_code == 404


def test_ses_callback_should_fail_if_invalid_json(client, mocker):
    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

    response = client.post(
        path='/notifications/email/ses',
        data="nonsense",
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'SES callback failed: invalid json'
    stats_mock.assert_not_called()


def test_ses_callback_should_autoconfirm_subscriptions(client, rmock, mocker):
    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

    endpoint = json.loads(ses_confirmation_callback())['SubscribeURL']
    rmock.request(
        "GET",
        endpoint,
        json={"status": "success"},
        status_code=200)

    response = client.post(
        path='/notifications/email/ses',
        data=ses_confirmation_callback(),
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert response.status_code == 200
    assert json_resp['result'] == 'success'
    assert json_resp['message'] == 'SES callback succeeded'
    stats_mock.assert_not_called()


def test_ses_callback_autoconfirm_raises_exception_if_not_200(client, rmock, mocker):
    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

    endpoint = json.loads(ses_confirmation_callback())['SubscribeURL']
    rmock.request(
        "GET",
        endpoint,
        json={"status": "not allowed"},
        status_code=405)

    with pytest.raises(HTTPError) as exc:
        client.post(
            path='/notifications/email/ses',
            data=ses_confirmation_callback(),
            headers=[('Content-Type', 'text/plain; charset=UTF-8')]
        )

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert exc.value.response.status_code == 405
    stats_mock.assert_not_called()


def test_ses_callback_should_fail_if_invalid_notification_type(client, mocker):
    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

    response = client.post(
        path='/notifications/email/ses',
        data=ses_invalid_notification_type_callback(),
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'SES callback failed: status Unknown not found'
    stats_mock.assert_not_called()


def test_ses_callback_should_fail_if_missing_message_id(client, mocker):
    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

    response = client.post(
        path='/notifications/email/ses',
        data=ses_missing_notification_id_callback(),
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'SES callback failed: messageId missing'
    stats_mock.assert_not_called()


def test_ses_callback_should_fail_if_notification_cannot_be_found(notify_db, notify_db_session, client, mocker):
    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

    response = client.post(
        path='/notifications/email/ses',
        data=ses_invalid_notification_id_callback(),
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'SES callback failed: notification either not found or already updated from sending. Status delivered for notification reference missing'  # noqa
    stats_mock.assert_not_called()


def test_ses_callback_should_update_notification_status(
        client,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
    with freeze_time('2001-01-01T12:00:00'):
        mocker.patch('app.statsd_client.incr')
        mocker.patch('app.statsd_client.timing_with_dates')
        stats_mock = mocker.patch(
            'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
        )

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
        statsd_client.timing_with_dates.assert_any_call(
            "callback.ses.elapsed-time", datetime.utcnow(), notification.sent_at
        )
        statsd_client.incr.assert_any_call("callback.ses.delivered")
        stats_mock.assert_called_once_with(notification)


def test_ses_callback_should_update_multiple_notification_status_sent(
        client,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):

    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

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
    stats_mock.assert_has_calls([
        call(notification1),
        call(notification2),
        call(notification3)
    ])


def test_ses_callback_should_set_status_to_temporary_failure(client,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template,
                                                             mocker):

    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

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
    stats_mock.assert_called_once_with(notification)


def test_ses_callback_should_not_set_status_once_status_is_delivered(client,
                                                                     notify_db,
                                                                     notify_db_session,
                                                                     sample_email_template,
                                                                     mocker):
    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

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
    assert json_resp['message'] == 'SES callback failed: notification either not found or already updated from sending. Status temporary-failure for notification reference ref'  # noqa
    assert get_notification_by_id(notification.id).status == 'delivered'
    stats_mock.assert_not_called()


def test_ses_callback_should_set_status_to_permanent_failure(client,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template,
                                                             mocker):
    stats_mock = mocker.patch(
        'app.notifications.notifications_ses_callback.create_outcome_notification_statistic_tasks'
    )

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
    stats_mock.assert_called_once_with(notification)


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


def ses_confirmation_callback():
    return b'{\n    "Type": "SubscriptionConfirmation",\n    "MessageId": "165545c9-2a5c-472c-8df2-7ff2be2b3b1b",\n    "Token": "2336412f37fb687f5d51e6e241d09c805a5a57b30d712f794cc5f6a988666d92768dd60a747ba6f3beb71854e285d6ad02428b09ceece29417f1f02d609c582afbacc99c583a916b9981dd2728f4ae6fdb82efd087cc3b7849e05798d2d2785c03b0879594eeac82c01f235d0e717736",\n    "TopicArn": "arn:aws:sns:us-west-2:123456789012:MyTopic",\n    "Message": "You have chosen to subscribe to the topic arn:aws:sns:us-west-2:123456789012:MyTopic.\\nTo confirm the subscription, visit the SubscribeURL included in this message.",\n    "SubscribeURL": "https://sns.us-west-2.amazonaws.com/?Action=ConfirmSubscription&TopicArn=arn:aws:sns:us-west-2:123456789012:MyTopic&Token=2336412f37fb687f5d51e6e241d09c805a5a57b30d712f794cc5f6a988666d92768dd60a747ba6f3beb71854e285d6ad02428b09ceece29417f1f02d609c582afbacc99c583a916b9981dd2728f4ae6fdb82efd087cc3b7849e05798d2d2785c03b0879594eeac82c01f235d0e717736",\n    "Timestamp": "2012-04-26T20:45:04.751Z",\n    "SignatureVersion": "1",\n    "Signature": "EXAMPLEpH+DcEwjAPg8O9mY8dReBSwksfg2S7WKQcikcNKWLQjwu6A4VbeS0QHVCkhRS7fUQvi2egU3N858fiTDN6bkkOxYDVrY0Ad8L10Hs3zH81mtnPk5uvvolIC1CXGu43obcgFxeL3khZl8IKvO61GWB6jI9b5+gLPoBc1Q=",\n    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/SimpleNotificationService-f3ecfb7224c7233fe7bb5f59f96de52f.pem"\n}'  # noqa
