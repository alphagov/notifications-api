from datetime import datetime

import boto3
import pytest
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from flask import current_app
from freezegun import freeze_time
from moto import mock_aws
from notifications_utils.recipient_validation.postal_address import PostalAddress

import app
from app.celery import provider_tasks
from app.celery.provider_tasks import (
    deliver_email,
    deliver_letter,
    deliver_sms,
    update_letter_to_sending,
)
from app.clients.email import EmailClientNonRetryableException
from app.clients.email.aws_ses import (
    AwsSesClientException,
    AwsSesClientThrottlingSendRateException,
)
from app.clients.letter.dvla import (
    DvlaDuplicatePrintRequestException,
    DvlaNonRetryableException,
    DvlaRetryableException,
    DvlaThrottlingException,
)
from app.clients.sms import SmsClientResponseException
from app.constants import (
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    NOTIFICATION_SENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
)
from app.exceptions import NotificationTechnicalFailureException
from tests.app.db import create_notification


def test_should_have_decorated_tasks_functions():
    assert deliver_sms.__wrapped__.__name__ == "deliver_sms"
    assert deliver_email.__wrapped__.__name__ == "deliver_email"
    assert deliver_letter.__wrapped__.__name__ == "deliver_letter"


def test_should_call_send_sms_to_provider_from_deliver_sms_task(sample_notification, mocker):
    mocker.patch("app.delivery.send_to_providers.send_sms_to_provider")

    deliver_sms(sample_notification.id)
    app.delivery.send_to_providers.send_sms_to_provider.assert_called_with(sample_notification)


def test_should_add_to_retry_queue_if_notification_not_found_in_deliver_sms_task(notify_db_session, mocker):
    mocker.patch("app.delivery.send_to_providers.send_sms_to_provider")
    mocker.patch("app.celery.provider_tasks.deliver_sms.retry")

    notification_id = app.create_uuid()

    deliver_sms(notification_id)
    app.delivery.send_to_providers.send_sms_to_provider.assert_not_called()
    app.celery.provider_tasks.deliver_sms.retry.assert_called_with(queue="retry-tasks", countdown=0)


def test_send_sms_should_not_switch_providers_on_non_provider_failure(sample_notification, mocker):
    mocker.patch("app.delivery.send_to_providers.send_sms_to_provider", side_effect=Exception("Non Provider Exception"))
    mock_dao_reduce_sms_provider_priority = mocker.patch(
        "app.delivery.send_to_providers.dao_reduce_sms_provider_priority"
    )
    mocker.patch("app.celery.provider_tasks.deliver_sms.retry")

    deliver_sms(sample_notification.id)

    assert mock_dao_reduce_sms_provider_priority.called is False


def test_should_retry_and_log_warning_if_SmsClientResponseException_for_deliver_sms_task(
    sample_notification, mocker, caplog
):
    mocker.patch(
        "app.delivery.send_to_providers.send_sms_to_provider",
        side_effect=SmsClientResponseException("something went wrong"),
    )
    mocker.patch("app.celery.provider_tasks.deliver_sms.retry")

    with caplog.at_level("WARNING"):
        deliver_sms(sample_notification.id)

    assert provider_tasks.deliver_sms.retry.called is True
    assert sample_notification.status == "created"
    assert f"SMS notification delivery for id: {sample_notification.id} failed" in caplog.messages


def test_should_retry_and_log_exception_for_non_SmsClientResponseException_exceptions_for_deliver_sms_task(
    sample_notification, mocker, caplog
):
    mocker.patch("app.delivery.send_to_providers.send_sms_to_provider", side_effect=Exception("something went wrong"))
    mocker.patch("app.celery.provider_tasks.deliver_sms.retry")

    with caplog.at_level("ERROR"):
        deliver_sms(sample_notification.id)

    assert provider_tasks.deliver_sms.retry.called is True
    assert sample_notification.status == "created"
    assert f"SMS notification delivery for id: {sample_notification.id} failed" in caplog.messages


def test_should_go_into_technical_error_if_exceeds_retries_on_deliver_sms_task(sample_notification, mocker, caplog):
    mocker.patch("app.delivery.send_to_providers.send_sms_to_provider", side_effect=Exception("EXPECTED"))
    mocker.patch("app.celery.provider_tasks.deliver_sms.retry", side_effect=MaxRetriesExceededError())

    with pytest.raises(NotificationTechnicalFailureException) as e, caplog.at_level("ERROR"):
        deliver_sms(sample_notification.id)
    assert str(sample_notification.id) in str(e.value)

    provider_tasks.deliver_sms.retry.assert_called_with(queue="retry-tasks", countdown=0)

    assert sample_notification.status == "technical-failure"
    assert f"SMS notification delivery for id: {sample_notification.id} failed" in caplog.messages


# end of deliver_sms task tests, now deliver_email task tests


def test_should_call_send_email_to_provider_from_deliver_email_task(sample_notification, mocker):
    mocker.patch("app.delivery.send_to_providers.send_email_to_provider")

    deliver_email(sample_notification.id)
    app.delivery.send_to_providers.send_email_to_provider.assert_called_with(sample_notification)


def test_should_add_to_retry_queue_if_notification_not_found_in_deliver_email_task(notify_api, mocker):
    mocker.patch("app.delivery.send_to_providers.send_email_to_provider")
    mocker.patch("app.celery.provider_tasks.deliver_email.retry")

    notification_id = app.create_uuid()

    deliver_email(notification_id)
    app.delivery.send_to_providers.send_email_to_provider.assert_not_called()
    app.celery.provider_tasks.deliver_email.retry.assert_called_with(queue="retry-tasks")


@pytest.mark.parametrize(
    "exception_class",
    [
        Exception(),
        AwsSesClientException(),
        AwsSesClientThrottlingSendRateException(),
    ],
)
def test_should_go_into_technical_error_if_exceeds_retries_on_deliver_email_task(
    sample_notification, mocker, exception_class
):
    mocker.patch("app.delivery.send_to_providers.send_email_to_provider", side_effect=exception_class)
    mocker.patch("app.celery.provider_tasks.deliver_email.retry", side_effect=MaxRetriesExceededError())

    with pytest.raises(NotificationTechnicalFailureException) as e:
        deliver_email(sample_notification.id)
    assert str(sample_notification.id) in str(e.value)

    provider_tasks.deliver_email.retry.assert_called_with(queue="retry-tasks")
    assert sample_notification.status == "technical-failure"


def test_should_technical_error_and_not_retry_if_EmailClientNonRetryableException(sample_notification, mocker):
    mocker.patch(
        "app.delivery.send_to_providers.send_email_to_provider",
        side_effect=EmailClientNonRetryableException("bad email"),
    )
    mocker.patch("app.celery.provider_tasks.deliver_email.retry")

    deliver_email(sample_notification.id)

    assert provider_tasks.deliver_email.retry.called is False
    assert sample_notification.status == "technical-failure"


def test_should_retry_and_log_exception_for_deliver_email_task(sample_notification, mocker, caplog):
    error_response = {"Error": {"Code": "SomeError", "Message": "some error message from amazon", "Type": "Sender"}}
    ex = ClientError(error_response=error_response, operation_name="opname")
    mocker.patch("app.delivery.send_to_providers.send_email_to_provider", side_effect=AwsSesClientException(str(ex)))
    mocker.patch("app.celery.provider_tasks.deliver_email.retry")

    with caplog.at_level("ERROR"):
        deliver_email(sample_notification.id)

    assert provider_tasks.deliver_email.retry.called is True
    assert sample_notification.status == "created"
    assert f"RETRY: Email notification {sample_notification.id} failed" in caplog.messages


def test_if_ses_send_rate_throttle_then_should_retry_and_log_warning(sample_notification, mocker, caplog):
    error_response = {"Error": {"Code": "Throttling", "Message": "Maximum sending rate exceeded.", "Type": "Sender"}}
    ex = ClientError(error_response=error_response, operation_name="opname")
    mocker.patch(
        "app.delivery.send_to_providers.send_email_to_provider",
        side_effect=AwsSesClientThrottlingSendRateException(str(ex)),
    )
    mocker.patch("app.celery.provider_tasks.deliver_email.retry")

    with caplog.at_level("WARNING"):
        deliver_email(sample_notification.id)

    assert provider_tasks.deliver_email.retry.called is True
    assert sample_notification.status == "created"
    assert not any(r.levelname == "ERROR" for r in caplog.records)
    assert f"RETRY: Email notification {sample_notification.id} was rate limited by SES" in caplog.messages


@freeze_time("2020-02-17 16:00:00")
def test_update_letter_to_sending(sample_letter_template):
    letter = create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_CREATED,
        created_at=datetime.now(),
    )
    update_letter_to_sending(letter)

    assert letter.status == NOTIFICATION_SENDING
    assert letter.sent_at == datetime.utcnow()
    assert letter.updated_at == datetime.utcnow()
    assert letter.sent_by == "dvla"


@mock_aws
@freeze_time("2020-02-17 16:00:00")
def test_deliver_letter(
    mocker,
    sample_letter_template,
    sample_organisation,
):
    mock_send_letter = mocker.patch("app.celery.provider_tasks.dvla_client.send_letter")

    letter = create_notification(
        template=sample_letter_template,
        to_field="A. User\nMy Street,\nLondon,\nSW1 1AA",
        personalisation={"address_line_1": "Provided as PDF"},
        status=NOTIFICATION_CREATED,
        reference="ref1",
        created_at=datetime.now(),
    )
    sample_letter_template.service.organisation = sample_organisation

    pdf_bucket = current_app.config["S3_BUCKET_LETTERS_PDF"]
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=pdf_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})
    s3.put_object(Bucket=pdf_bucket, Key="2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF", Body=b"file"),

    deliver_letter(letter.id)

    mock_send_letter.assert_called_once_with(
        notification_id=str(letter.id),
        reference="ref1",
        address=PostalAddress("A. User\nMy Street\nLondon\nSW1 1AA\n\n\n", True),
        postage="second",
        service_id=str(letter.service_id),
        organisation_id=str(sample_organisation.id),
        pdf_file=b"file",
    )
    assert letter.status == NOTIFICATION_SENDING
    assert letter.sent_by == "dvla"


@mock_aws
@freeze_time("2020-02-17 16:00:00")
def test_deliver_letter_when_file_is_not_in_S3_logs_an_error(mocker, sample_letter_template, sample_organisation):
    mock_send_letter = mocker.patch("app.celery.provider_tasks.dvla_client.send_letter")
    mock_retry = mocker.patch("app.celery.provider_tasks.deliver_letter.retry", side_effect=MaxRetriesExceededError())

    letter = create_notification(
        template=sample_letter_template,
        to_field="A. User",
        personalisation={
            "addressline1": "A. User",
            "addressline2": "My Street",
            "addressline3": "London",
            "addressline4": "SW1 1AA",
            "addressline5": None,
            "addressline6": None,
            "addressline7": None,
        },
        status=NOTIFICATION_CREATED,
        reference="ref1",
        created_at=datetime.now(),
    )
    sample_letter_template.service.organisation = sample_organisation

    pdf_bucket = current_app.config["S3_BUCKET_LETTERS_PDF"]
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=pdf_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})

    with pytest.raises(NotificationTechnicalFailureException) as e:
        deliver_letter(letter.id)

    assert str(letter.id) in str(e.value)
    assert not mock_retry.called
    assert not mock_send_letter.called
    assert letter.status == NOTIFICATION_TECHNICAL_FAILURE


@mock_aws
@freeze_time("2020-02-17 16:00:00")
@pytest.mark.parametrize(
    "exception_type, error_class",
    [
        ("retryable_error", DvlaRetryableException()),
        ("throttling_error", DvlaThrottlingException()),
    ],
)
def test_deliver_letter_retries_when_there_is_a_retryable_exception(
    mocker, sample_letter_template, sample_organisation, exception_type, error_class, caplog
):
    mocker.patch("app.celery.provider_tasks.dvla_client.send_letter", side_effect=error_class)
    mock_retry = mocker.patch("app.celery.provider_tasks.deliver_letter.retry")

    letter = create_notification(
        template=sample_letter_template,
        to_field="A. User",
        personalisation={
            "addressline1": "A. User",
            "addressline2": "My Street",
            "addressline3": "London",
            "addressline4": "SW1 1AA",
            "addressline5": None,
            "addressline6": None,
            "addressline7": None,
        },
        status=NOTIFICATION_CREATED,
        reference="ref1",
        created_at=datetime.now(),
    )
    sample_letter_template.service.organisation = sample_organisation

    pdf_bucket = current_app.config["S3_BUCKET_LETTERS_PDF"]
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=pdf_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})
    s3.put_object(Bucket=pdf_bucket, Key="2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF", Body=b"file"),

    with caplog.at_level("WARNING"):
        deliver_letter(letter.id)

    assert mock_retry.called is True
    assert letter.status == NOTIFICATION_CREATED

    if exception_type == "retryable_error":
        assert any(r.levelname == "ERROR" for r in caplog.records)
        assert f"RETRY: Letter notification {letter.id} failed" in caplog.messages
    else:
        assert any(r.levelname == "WARNING" for r in caplog.records)
        assert f"RETRY: Letter notification {letter.id} was rate limited by DVLA" in caplog.messages


@mock_aws
@freeze_time("2020-02-17 16:00:00")
def test_deliver_letter_logs_a_warning_when_the_print_request_is_duplicate(
    mocker, sample_letter_template, sample_organisation, caplog
):
    mocker.patch("app.celery.provider_tasks.dvla_client.send_letter", side_effect=DvlaDuplicatePrintRequestException())
    mock_retry = mocker.patch("app.celery.provider_tasks.deliver_letter.retry")

    letter = create_notification(
        template=sample_letter_template,
        to_field="A. User",
        personalisation={
            "addressline1": "A. User",
            "addressline2": "My Street",
            "addressline3": "London",
            "addressline4": "SW1 1AA",
            "addressline5": None,
            "addressline6": None,
            "addressline7": None,
        },
        status=NOTIFICATION_CREATED,
        reference="ref1",
        created_at=datetime.now(),
    )
    sample_letter_template.service.organisation = sample_organisation

    pdf_bucket = current_app.config["S3_BUCKET_LETTERS_PDF"]
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=pdf_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})
    s3.put_object(Bucket=pdf_bucket, Key="2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF", Body=b"file"),

    with caplog.at_level("WARNING"):
        deliver_letter(letter.id)

    assert not mock_retry.called
    assert letter.status == NOTIFICATION_CREATED
    assert f"Duplicate deliver_letter task called for notification {letter.id}" in caplog.messages


@freeze_time("2020-02-17 16:00:00")
def test_deliver_letter_logs_an_error_when_test_letter(mocker, sample_letter_template, caplog):
    mock_send = mocker.patch("app.celery.provider_tasks.dvla_client.send_letter")
    mock_retry = mocker.patch("app.celery.provider_tasks.deliver_letter.retry")

    letter = create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_CREATED,
        key_type=KEY_TYPE_TEST,
    )

    with caplog.at_level("ERROR"):
        deliver_letter(letter.id)

    assert not mock_retry.called
    assert not mock_send.called
    assert f"deliver_letter task called for notification {letter.id} with key type test" in caplog.messages


@freeze_time("2020-02-17 16:00:00")
def test_deliver_letter_logs_an_error_when_letter_not_created(mocker, sample_letter_template, caplog):
    mock_send = mocker.patch("app.celery.provider_tasks.dvla_client.send_letter")
    mock_retry = mocker.patch("app.celery.provider_tasks.deliver_letter.retry")

    letter = create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_SENDING,
        key_type=KEY_TYPE_TEST,
    )

    with caplog.at_level("WARNING"):
        deliver_letter(letter.id)

    assert not mock_retry.called
    assert not mock_send.called
    assert f"deliver_letter task called for notification {letter.id} in status sending" in caplog.messages


@mock_aws
@freeze_time("2020-02-17 16:00:00")
@pytest.mark.parametrize("exception_class", [DvlaNonRetryableException(), Exception()])
def test_deliver_letter_when_there_is_a_non_retryable_error(
    mocker, sample_letter_template, sample_organisation, exception_class
):
    mocker.patch("app.celery.provider_tasks.dvla_client.send_letter", side_effect=exception_class)
    mock_retry = mocker.patch("app.celery.provider_tasks.deliver_letter.retry")

    letter = create_notification(
        template=sample_letter_template,
        to_field="A. User",
        personalisation={
            "addressline1": "A. User",
            "addressline2": "My Street",
            "addressline3": "London",
            "addressline4": "SW1 1AA",
            "addressline5": None,
            "addressline6": None,
            "addressline7": None,
        },
        status=NOTIFICATION_CREATED,
        reference="ref1",
        created_at=datetime.now(),
    )
    sample_letter_template.service.organisation = sample_organisation

    pdf_bucket = current_app.config["S3_BUCKET_LETTERS_PDF"]
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=pdf_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})
    s3.put_object(Bucket=pdf_bucket, Key="2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF", Body=b"file"),

    with pytest.raises(NotificationTechnicalFailureException) as e:
        deliver_letter(letter.id)

    assert str(letter.id) in str(e.value)
    assert not mock_retry.called
    assert letter.status == NOTIFICATION_TECHNICAL_FAILURE


@mock_aws
@freeze_time("2020-02-17 16:00:00")
def test_deliver_letter_when_max_retries_are_reached(mocker, sample_letter_template, sample_organisation):
    mocker.patch("app.celery.provider_tasks.dvla_client.send_letter", side_effect=DvlaRetryableException())
    mock_retry = mocker.patch("app.celery.provider_tasks.deliver_letter.retry", side_effect=MaxRetriesExceededError())

    letter = create_notification(
        template=sample_letter_template,
        to_field="A. User",
        personalisation={
            "addressline1": "A. User",
            "addressline2": "My Street",
            "addressline3": "London",
            "addressline4": "SW1 1AA",
            "addressline5": None,
            "addressline6": None,
            "addressline7": None,
        },
        status="created",
        reference="ref1",
        created_at=datetime.now(),
    )
    sample_letter_template.service.organisation = sample_organisation

    pdf_bucket = current_app.config["S3_BUCKET_LETTERS_PDF"]
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=pdf_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})
    s3.put_object(Bucket=pdf_bucket, Key="2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF", Body=b"file"),

    with pytest.raises(NotificationTechnicalFailureException) as e:
        deliver_letter(letter.id)

    assert mock_retry.called is True
    assert str(letter.id) in str(e.value)
    assert letter.status == NOTIFICATION_TECHNICAL_FAILURE
