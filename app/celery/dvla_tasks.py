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
