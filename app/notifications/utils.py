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
