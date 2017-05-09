from flask import current_app
import requests


def confirm_subscription(confirmation_request):
    url = confirmation_request.get('SubscribeURL')
    if not url:
        current_app.logger.warning("SubscribeURL does not exist or empty")
        return

    response = requests.get(url)
    try:
        response.raise_for_status()
    except Exception as e:
        current_app.logger.warning("Response: {}".format(response.text))
        raise e

    return confirmation_request['TopicArn']


def autoconfirm_subscription(req_json):
    if req_json.get('Type') == 'SubscriptionConfirmation':
        current_app.logger.info("SNS subscription confirmation url: {}".format(req_json['SubscribeURL']))
        subscribed_topic = confirm_subscription(req_json)
        return subscribed_topic
