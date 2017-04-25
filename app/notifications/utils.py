import requests


def confirm_subscription(confirmation_request):
    url = confirmation_request['SubscribeURL']
    response = requests.get(url)
    if response.code < 400:
        return confirmation_request['TopicArn']
