from datetime import datetime

from flask import json
from freezegun import freeze_time

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


def test_ses_callback_should_fail_if_invalid_json(client):
    response = client.post(
        path='/notifications/email/ses',
        data="nonsense",
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'SES callback failed: invalid json'


def test_ses_callback_should_fail_if_invalid_notification_type(client):
    response = client.post(
        path='/notifications/email/ses',
        data=ses_invalid_notification_type_callback(),
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'SES callback failed: status Unknown not found'


def test_ses_callback_should_fail_if_missing_message_id(client):
    response = client.post(
        path='/notifications/email/ses',
        data=ses_missing_notification_id_callback(),
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'SES callback failed: messageId missing'


def test_ses_callback_should_fail_if_notification_cannot_be_found(notify_db, notify_db_session, client):
    response = client.post(
        path='/notifications/email/ses',
        data=ses_invalid_notification_id_callback(),
        headers=[('Content-Type', 'text/plain; charset=UTF-8')]
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'SES callback failed: notification either not found or already updated from sending. Status delivered for notification reference missing'  # noqa


def test_ses_callback_should_update_notification_status(
        client,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
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
        statsd_client.timing_with_dates.assert_any_call(
            "callback.ses.elapsed-time", datetime.utcnow(), notification.sent_at
        )
        statsd_client.incr.assert_any_call("callback.ses.delivered")


def test_ses_callback_should_update_multiple_notification_status_sent(
        client,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
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


def test_ses_callback_should_set_status_to_temporary_failure(client,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template):
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


def test_ses_callback_should_not_set_status_once_status_is_delivered(client,
                                                                     notify_db,
                                                                     notify_db_session,
                                                                     sample_email_template):
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


def test_ses_callback_should_set_status_to_permanent_failure(client,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template):
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
