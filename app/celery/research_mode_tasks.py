import json

from flask import current_app
from app import notify_celery
from requests import request, RequestException, HTTPError

from app.models import SMS_TYPE

temp_fail = "07700900003"
perm_fail = "07700900002"
delivered = "07700900001"

delivered_email = "delivered@simulator.notify"
perm_fail_email = "perm-fail@simulator.notify"
temp_fail_email = "temp-fail@simulator.notify"


@notify_celery.task(name="send-mmg-response")
def send_sms_response(provider, reference, to):
    if provider == "mmg":
        body = mmg_callback(reference, to)
        headers = {"Content-type": "application/json"}
    else:
        headers = {"Content-type": "application/x-www-form-urlencoded"}
        body = firetext_callback(reference, to)
    make_request(SMS_TYPE, provider, body, headers)


@notify_celery.task(name="send-ses-response")
def send_email_response(provider, reference, to):
    if to == perm_fail_email:
        body = ses_hard_bounce_callback(reference)
    elif to == temp_fail_email:
        body = ses_soft_bounce_callback(reference)
    else:
        body = ses_notification_callback(reference)

    make_request('email', provider, body, headers={"Content-type": "application/json"})


def make_request(notification_type, provider, data, headers):
    api_call = "{}/notifications/{}/{}".format(current_app.config["API_HOST_NAME"], notification_type, provider)

    try:
        response = request(
            "POST",
            api_call,
            headers=headers,
            data=data
        )
        response.raise_for_status()
    except RequestException as e:
        api_error = HTTPError(e)
        current_app.logger.error(
            "API {} request on {} failed with {}".format(
                "POST",
                api_call,
                api_error.response
            )
        )
        raise api_error
    finally:
        current_app.logger.info("Mocked provider callback request finished")
    return response.json()


def mmg_callback(notification_id, to):
    """
        status: 3 - delivered
        status: 4 - expired (temp failure)
        status: 5 - rejected (perm failure)
    """

    if to == temp_fail:
        status = "4"
    elif to == perm_fail:
        status = "5"
    else:
        status = "3"

    return json.dumps({"reference": "mmg_reference",
                       "CID": str(notification_id),
                       "MSISDN": to,
                       "status": status,
                       "deliverytime": "2016-04-05 16:01:07"})


def firetext_callback(notification_id, to):
    """
        status: 0 - delivered
        status: 1 - perm failure
    """
    if to == perm_fail:
        status = "1"
    else:
        status = "0"
    return {
        'mobile': to,
        'status': status,
        'time': '2016-03-10 14:17:00',
        'reference': notification_id
    }


def ses_notification_callback(reference):
    return '{  "Type" : "Notification",  "MessageId" : "%s",  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"%s\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",  "Timestamp" : "2016-03-14T12:35:26.665Z",  "SignatureVersion" : "1",  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"}' % (reference, reference)  # noqa


def ses_hard_bounce_callback(reference):
    return '{  "Type" : "Notification",  "MessageId" : "%s",  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",  "Message" : "{\\"notificationType\\":\\"Bounce\\",\\"bounce\\":{\\"bounceType\\":\\"Permanent\\",\\"bounceSubType\\":\\"General\\"}, \\"mail\\":{\\"messageId\\":\\"%s\\",\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",  "Timestamp" : "2016-03-14T12:35:26.665Z",  "SignatureVersion" : "1",  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"}' % (reference, reference)  # noqa


def ses_soft_bounce_callback(reference):
    return '{  "Type" : "Notification",  "MessageId" : "%s",  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",  "Message" : "{\\"notificationType\\":\\"Bounce\\",\\"bounce\\":{\\"bounceType\\":\\"Undetermined\\",\\"bounceSubType\\":\\"General\\"}, \\"mail\\":{\\"messageId\\":\\"%s\\",\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",  "Timestamp" : "2016-03-14T12:35:26.665Z",  "SignatureVersion" : "1",  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"}' % (reference, reference)  # noqa
