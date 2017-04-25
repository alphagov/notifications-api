import requests


def confirm_subscription(confirmation_request):
    url = confirmation_request['SubscribeURL']
    response = requests.get(url)
    response.raise_for_status()
    return confirmation_request['TopicArn']
