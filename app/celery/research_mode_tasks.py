import json

from flask import current_app
from requests import request, RequestException, HTTPError

from app.models import SMS_TYPE
from app.config import QueueNames
from app.celery.callback_tasks import process_ses_results

temp_fail = "7700900003"
perm_fail = "7700900002"
delivered = "7700900001"

delivered_email = "delivered@simulator.notify"
perm_fail_email = "perm-fail@simulator.notify"
temp_fail_email = "temp-fail@simulator.notify"


def send_sms_response(provider, reference, to):
    if provider == "mmg":
        body = mmg_callback(reference, to)
        headers = {"Content-type": "application/json"}
    else:
        headers = {"Content-type": "application/x-www-form-urlencoded"}
        body = firetext_callback(reference, to)
        # to simulate getting a temporary_failure from firetext
        # we need to send a pending status updated then a permanent-failure
        if body['status'] == '2':  # pending status
            make_request(SMS_TYPE, provider, body, headers)
            # 1 is a declined status for firetext, will result in a temp-failure
            body = {'mobile': to,
                    'status': "1",
                    'time': '2016-03-10 14:17:00',
                    'reference': reference
                    }

    make_request(SMS_TYPE, provider, body, headers)


def send_email_response(reference, to):
    if to == perm_fail_email:
        body = ses_hard_bounce_callback(reference)
    elif to == temp_fail_email:
        body = ses_soft_bounce_callback(reference)
    else:
        body = ses_notification_callback(reference)

    process_ses_results.apply_async([body], queue=QueueNames.RESEARCH_MODE)


def make_request(notification_type, provider, data, headers):
    api_call = "{}/notifications/{}/{}".format(current_app.config["API_HOST_NAME"], notification_type, provider)

    try:
        response = request(
            "POST",
            api_call,
            headers=headers,
            data=data,
            timeout=60
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

    if to.strip().endswith(temp_fail):
        status = "4"
    elif to.strip().endswith(perm_fail):
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
    if to.strip().endswith(perm_fail):
        status = "1"
    elif to.strip().endswith(temp_fail):
        status = "2"
    else:
        status = "0"
    return {
        'mobile': to,
        'status': status,
        'time': '2016-03-10 14:17:00',
        'reference': notification_id
    }


def ses_notification_callback(reference):
    return {
        'EventSource': 'aws:sns',
        'EventVersion': '1.0',
        'EventSubscriptionArn': 'arn:aws:sns:eu-west-1:302763885840:ses_notifications:27447d51-7008-4d9c-83f2-519983b60937',
        'Sns': {
            'Type': 'Notification',
            'MessageId': '8e83c020-3a50-5957-a2ca-92a8ee9baa0a',
            'TopicArn': 'arn:aws:sns:eu-west-1:302763885840:ses_notifications',
            'Subject': None,
            'Message': '''{"notificationType":"Delivery","mail":{"timestamp":"2017-11-17T12:14:01.643Z","source":"\\"sakis\\" <sakis@notify.works>","sourceArn":"arn:aws:ses:eu-west-1:302763885840:identity/notify.works","sourceIp":"52.208.24.161","sendingAccountId":"302763885840","messageId":"0102015fc9e669ab-d1395dba-84c7-4311-9f25-405396a3f7aa-000000","destination":["success@simulator.amazonses.com"],"headersTruncated":false,"headers":[{"name":"From","value":"sakis <sakis@notify.works>"},{"name":"To","value":"success@simulator.amazonses.com"},{"name":"Subject","value":"lambda test"},{"name":"MIME-Version","value":"1.0"},{"name":"Content-Type","value":"multipart/alternative; boundary=\\"----=_Part_617203_1627511946.1510920841645\\""}],"commonHeaders":{"from":["sakis <sakis@notify.works>"],"to":["success@simulator.amazonses.com"],"subject":"lambda test"}},"delivery":{"timestamp":"2017-11-17T12:14:03.646Z","processingTimeMillis":2003,"recipients":["success@simulator.amazonses.com"],"smtpResponse":"250 2.6.0 Message received","remoteMtaIp":"207.171.163.188","reportingMTA":"a7-32.smtp-out.eu-west-1.amazonses.com"}}', 'Timestamp': '2017-11-17T12:14:03.710Z', 'SignatureVersion': '1', 'Signature': 'IxQPpK5kHVSiYhFqWjH35ElZSUOkE29hDcdCjFrA6Cx51Fw5ZNyFGsYJQsCskVEIXteTrn/9VU9zeW5oSf81dbGzv5GnFF4iq8hq+WISQ3etVGx9cOzRABudt82okoIPLU71dsENwj3scibVvsBSP8vD4NJsnOXVfVo1CczumbDT601dFomF45u1bRpg684zUOxvZBpStUfkFaBkDrWp9yt6j5SuDx+AqC0nuQdGPN0+LFbLXN20SZmUwqDiX89xm2JlPBaWimnm0/jBRAqLkSJcix7ssD6ELsCIebljzggibnKzQo3vQV1Frji6+713WlYC7lnziNhVT1VL1tCrhA==', 'SigningCertUrl': 'https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-433026a4050d206028891664da859041.pem', 'UnsubscribeUrl': 'https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:ses_notifications:27447d51-7008-4d9c-83f2-519983b60937''',  # noqa
            'MessageAttributes': {}
        }
    }


def ses_hard_bounce_callback(reference):
    return {
        'Message': '{"notificationType":"Bounce","bounce":{"bounceType":"Permanent","bounceSubType":"General"}, "mail":{"messageId":"%s","timestamp":"2016-03-14T12:35:25.909Z","source":"test@test-domain.com","sourceArn":"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify","sendingAccountId":"123456789012","destination":["testing@digital.cabinet-office.gov.uk"]},"delivery":{"timestamp":"2016-03-14T12:35:26.567Z","processingTimeMillis":658,"recipients":["testing@digital.cabinet-office.gov.uk"],"smtpResponse":"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp","reportingMTA":"a6-238.smtp-out.eu-west-1.amazonses.com"}}' % reference,  # noqa
        'MessageId': reference,
        'Signature': 'X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==',  # noqa
        'SignatureVersion': '1',
        'SigningCertURL': 'https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem',  # noqa
        'Timestamp': '2016-03-14T12:35:26.665Z',
        'TopicArn': 'arn:aws:sns:eu-west-1:123456789012:testing',
        'Type': 'Notification',
        'UnsubscribeURL': 'https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da'  # noqa
    }


def ses_soft_bounce_callback(reference):
    return {
        'Message': '{"notificationType":"Bounce","bounce":{"bounceType":"Temporary","bounceSubType":"General"}, "mail":{"messageId":"%s","timestamp":"2016-03-14T12:35:25.909Z","source":"test@test-domain.com","sourceArn":"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify","sendingAccountId":"123456789012","destination":["testing@digital.cabinet-office.gov.uk"]},"delivery":{"timestamp":"2016-03-14T12:35:26.567Z","processingTimeMillis":658,"recipients":["testing@digital.cabinet-office.gov.uk"],"smtpResponse":"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp","reportingMTA":"a6-238.smtp-out.eu-west-1.amazonses.com"}}' % reference,  # noqa
        'MessageId': reference,
        'Signature': 'X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==',  # noqa
        'SignatureVersion': '1',
        'SigningCertURL': 'https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem',  # noqa
        'Timestamp': '2016-03-14T12:35:26.665Z',
        'TopicArn': 'arn:aws:sns:eu-west-1:123456789012:testing',
        'Type': 'Notification',
        'UnsubscribeURL': 'https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da'  # noqa
    }
