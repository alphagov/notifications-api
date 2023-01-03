import functools
import uuid

import requests

from app import notify_celery
from app.clients.letter.dvla import DVLAClient
from app.config import QueueNames


@functools.cache
def get_client() -> DVLAClient:
    # Let's not do it this way in prod - PoC implementation only
    # This is used because we import this whole module for all celery workers, but only want to load the creds
    # for workers which actually handle DVLA tasks.
    client = DVLAClient()
    client.load_credentials()
    return client


@notify_celery.task(name="authenticate-to-dvla-api", queue=QueueNames.LETTERS)
def authenticate_to_dvla_api():
    print("authenticate_to_dvla_api")
    client = get_client()
    client.authenticate()


@notify_celery.task(name="get-dvla-print-job", queue=QueueNames.LETTERS)
def get_dvla_print_job():
    print("get_dvla_print_job")
    client = get_client()
    try:
        client.get_print_job(str(uuid.uuid4()))
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print("Got 404 from DVLA Letters API - successfully authenticated")
        else:
            raise e


@notify_celery.task(name="rotate-dvla-api-password", queue=QueueNames.LETTERS)
def rotate_dvla_api_password():
    """This will generate a new random password for the DVLA API, and store it in AWS
    Parameter Store.

    DVLA API passwords last 90 days. We should schedule this task to run weekly so that
    we never get into the position where the code is trying to use a password that has expired.
    """
    print("rotate_dvla_api_password")
    client = get_client()
    client.rotate_password()
