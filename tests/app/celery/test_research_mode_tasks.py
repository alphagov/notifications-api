from flask import json
from app.celery.research_mode_tasks import (
    send_sms_response,
    send_email_response,
    mmg_callback,
    firetext_callback,
    ses_notification_callback,
    ses_hard_bounce_callback,
    ses_soft_bounce_callback
)


def test_make_mmg_callback(notify_api, rmock):
    endpoint = "http://localhost:6011/notifications/sms/mmg"
    rmock.request(
        "POST",
        endpoint,
        json={"status": "success"},
        status_code=200)
    send_sms_response("mmg", "1234", "07811111111")

    assert rmock.called


def test_make_firetext_callback(notify_api, rmock):
    endpoint = "http://localhost:6011/notifications/sms/firetext"
    rmock.request(
        "POST",
        endpoint,
        data="some data",
        status_code=200)
    send_sms_response("firetext", "1234", "07811111111")

    assert rmock.called


def test_make_ses_callback(notify_api, rmock):
    endpoint = "http://localhost:6011/notifications/email/ses"
    rmock.request(
        "POST",
        endpoint,
        json={"status": "success"},
        status_code=200)
    send_email_response("ses", "1234", "test@test.com")

    assert rmock.called


def test_delivered_mmg_callback():
    data = json.loads(mmg_callback("1234", "07811111111"))
    assert data['MSISDN'] == "07811111111"
    assert data['status'] == "0"
    assert data['reference'] == "mmg_reference"
    assert data['CID'] == "1234"


def test_perm_failure_mmg_callback():
    data = json.loads(mmg_callback("1234", "07822222222"))
    assert data['MSISDN'] == "07822222222"
    assert data['status'] == "5"
    assert data['reference'] == "mmg_reference"
    assert data['CID'] == "1234"


def test_temp_failure_mmg_callback():
    data = json.loads(mmg_callback("1234", "07833333333"))
    assert data['MSISDN'] == "07833333333"
    assert data['status'] == "4"
    assert data['reference'] == "mmg_reference"
    assert data['CID'] == "1234"


def test_delivered_firetext_callback():
    assert firetext_callback("1234", "07811111111") == "mobile=07811111111&status=0&time=2016-03-10 14:17:00&reference=1234"  # noqa


def test_failure_firetext_callback():
    assert firetext_callback("1234", "07822222222") == "mobile=07822222222&status=1&time=2016-03-10 14:17:00&reference=1234"  # noqa


def test_delivered_ses_callback():
    assert ses_notification_callback("my-reference") == '{\n  "Type" : "Notification",\n  "MessageId" : "my-reference",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"ref\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def test_ses_hard_bounce_callback():
    assert ses_hard_bounce_callback("my-reference") == '{\n  "Type" : "Notification",\n  "MessageId" : "my-reference",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Bounce\\",\\"bounce\\":{\\"bounceType\\":\\"Permanent\\",\\"bounceSubType\\":\\"General\\"}, \\"mail\\":{\\"messageId\\":\\"ref\\",\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_soft_bounce_callback():
    assert ses_soft_bounce_callback("my-reference") == '{\n  "Type" : "Notification",\n  "MessageId" : "my-reference",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Bounce\\",\\"bounce\\":{\\"bounceType\\":\\"Undetermined\\",\\"bounceSubType\\":\\"General\\"}, \\"mail\\":{\\"messageId\\":\\"ref\\",\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa
