import functools
import time
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


@notify_celery.task(name="rotate-dvla-api-key", queue=QueueNames.LETTERS)
def rotate_dvla_api_key():
    print("rotate_dvla_api_key")
    client = get_client()
    client.rotate_api_key()


def queue_reauth_jwt_expiry_flow():
    """
    Run a worker with:
        aws-vault exec local_<name> --duration=10h -- celery \
            -A run_celery.notify_celery worker \
            -Q letter-tasks \
            --pidfile='/tmp/celery-dvla.pid' \
            --log-level=INFO \
            --concurrency=2

    This will give us two celery workers that can process tasks independently.

    This flow checks that when JWT token expires, worker will re-authenticate to get a new token.
    This requires waiting for JWT expiry.
    """
    # Check that each client can:
    #   1) generate a JWT token when it doesn't have one yet
    #   2) Re-use that JWT token without needing to re-authenticate
    print("Step 1: 4x get_dvla_print_job")
    for _ in range(4):
        get_dvla_print_job.apply_async()

    # # We sleep for an hour, which should mean all the JWT tokens are then invalid.
    print("Step 2: Sleep for an hour (let JWT expire)")
    time.sleep(3610)

    # Both clients have the correct password, should just need to fetch a new JWT.
    print("Step 3: 8x get_dvla_print_job")
    for _ in range(8):
        get_dvla_print_job.apply_async()


def queue_reauth_password_rotation_flow():
    """
    Run a worker with:
        aws-vault exec local_<name> --duration=10h -- celery \
            -A run_celery.notify_celery worker \
            -Q letter-tasks \
            --pidfile='/tmp/celery-dvla.pid' \
            --log-level=INFO \
            --concurrency=2

    This will give us two celery workers that can process tasks independently.

    This flow checks recovery from rotated passwords. This requires waiting for JWT expiry.
    """
    # Check that each client can:
    #   1) generate a JWT token when it doesn't have one yet
    #   2) Re-use that JWT token without needing to re-authenticate
    print("Step 1: 4x get_dvla_print_job")
    for _ in range(4):
        get_dvla_print_job.apply_async()

    time.sleep(30)

    # Rotate the password in one of the clients
    # Client 1 will automatically store the new password. The existing JWT will remain valid for 1 hour.
    # Client 2 will not know the password has changed. The existing JWT will remain valid for 1 hour.
    print("Step 2: 1x rotate_dvla_api_password, 6x get_dvla_print_job")
    rotate_dvla_api_password.apply_async()
    time.sleep(10)
    for _ in range(6):
        get_dvla_print_job.apply_async()

    # # We sleep for an hour, which should mean all the JWT tokens are then invalid.
    print("Step 3: Sleep for an hour (let JWT expire)")
    time.sleep(3600)

    # Client 1 will already know the new password, so it can ask for a new JWT token without needing to fetch the
    #   password from SSM.
    # Client 2 will not know the password has changed. It will try the request, fail, generate a new JWT with the old
    #   password and fail again, then go to AWS to refresh the username/password/api key and finally generate a new JWT
    #   token, which should succeed.
    print("Step 4: 20x get_dvla_print_job")
    for _ in range(20):
        get_dvla_print_job.apply_async()


def queue_reauth_api_key_rotation_flow():
    """
    Run a worker with:
        aws-vault exec local_<name> --duration=10h -- celery \
            -A run_celery.notify_celery worker \
            -Q letter-tasks \
            --pidfile='/tmp/celery-dvla.pid' \
            --log-level=INFO \
            --concurrency=2

    This will give us two celery workers that can process tasks independently.

    This flow validates that the clients can automatically detect and recover from rotated API keys.
    """
    # Check that each client can:
    #   1) generate a JWT token when it doesn't have one yet
    #   2) Re-use that JWT token without needing to re-authenticate
    print("Step 1: 4x get_dvla_print_job")
    for _ in range(4):
        get_dvla_print_job.apply_async()

    time.sleep(10)

    # Rotate the API key on one of the clients.
    # This will immediately kill all JWT tokens generated using the old API key.
    # Client 1 will update and remember the new API key, so can immediately generate a new JWT token without hitting
    #    SSM.
    # Client 2 will not know the API key has changed. It will go through the full re-auth flow: generate a new JWT,
    #    fail, and then fetch username/password/API key from SSM and generate another JWT.
    print("Step 5: 1x rotate_dvla_api_key, 40x get_dvla_print_job")
    rotate_dvla_api_key.apply_async()
    for _ in range(20):
        time.sleep(1)
        get_dvla_print_job.apply_async()
        get_dvla_print_job.apply_async()
