import json
from datetime import datetime

from app.celery.callback_tasks import process_ses_results

from tests.app.db import create_notification


def test_process_ses_results(sample_email_template):
    create_notification(
        sample_email_template,
        reference='ref1',
        sent_at=datetime.utcnow(),
        status='sending')

    response = json.loads(ses_notification_callback())
    assert process_ses_results(response=response) is None


def test_process_ses_results_does_not_retry_if_errors(notify_db, mocker):
    mocked = mocker.patch('app.celery.callback_tasks.process_ses_results.retry')
    response = json.loads(ses_notification_callback())
    process_ses_results(response=response)
    assert mocked.call_count == 0


def test_process_ses_results_retry_called(notify_db, mocker):
    mocker.patch("app.dao.notifications_dao.update_notification_status_by_reference", side_effect=Exception("EXPECTED"))
    mocked = mocker.patch('app.celery.callback_tasks.process_ses_results.retry')
    response = json.loads(ses_notification_callback())
    process_ses_results(response=response)
    assert mocked.call_count != 0


def ses_notification_callback():
    return '{\n  "Type" : "Notification",\n  "MessageId" : "ref1",' \
           '\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",' \
           '\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",' \
           '\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",' \
           '\\"source\\":\\"test@test-domain.com\\",' \
           '\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",' \
           '\\"sendingAccountId\\":\\"123456789012\\",' \
           '\\"messageId\\":\\"ref1\\",' \
           '\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},' \
           '\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",' \
           '\\"processingTimeMillis\\":658,' \
           '\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],' \
           '\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",' \
           '\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",' \
           '\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",' \
           '\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUt' \
           'OowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYL' \
           'VSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMA' \
           'PmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",' \
           '\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750' \
           'dd426d95ee9390147a5624348ee.pem",' \
           '\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&S' \
           'ubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'
