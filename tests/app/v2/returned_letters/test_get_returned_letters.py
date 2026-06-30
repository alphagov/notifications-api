import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import call

from freezegun import freeze_time

from app.constants import NOTIFICATION_RETURNED_LETTER
from app.utils import DATETIME_FORMAT_NO_TIMEZONE
from tests.app.db import (
    create_api_key,
    create_job,
    create_notification,
    create_notification_history,
    create_returned_letter,
    create_service,
    create_template,
)


@freeze_time("2026-06-22 13:30")
def test_v2_get_returned_letter_summary(mocker, api_client_request, sample_service):
    create_returned_letter(sample_service, reported_at=datetime.now(UTC) - timedelta(days=3))
    create_returned_letter(sample_service, reported_at=datetime.now(UTC))
    create_returned_letter(sample_service, reported_at=datetime.now(UTC))

    mock_redis_set = mocker.patch(
        "app.redis_store.set",
    )

    response = api_client_request.get(
        sample_service.id,
        "v2_returned_letters.get_returned_letter_summary",
        _expected_status=200,
    )

    assert len(response) == 2

    data = [
        {"returned_letter_count": 2, "report_date": "2026-06-22"},
        {"returned_letter_count": 1, "report_date": "2026-06-19"},
    ]

    assert response == data

    cache_key = f"service-{sample_service.id}-returned-letter-summary"

    assert mock_redis_set.call_args_list[1] == call(cache_key, json.dumps(data), ex=86400)


def test_v2_get_returned_letter_summary_raises_error_for_non_live_keys(api_client_request, sample_service):
    api_client_request.get(
        sample_service.id,
        "v2_returned_letters.get_returned_letter_summary",
        _api_key_type="test",
        _expected_status=403,
    )


@freeze_time("2026-06-23 13:30")
def test_v2_get_returned_endpoint(api_client_request, sample_letter_template):
    job = create_job(template=sample_letter_template)
    letter_from_job = create_notification(
        template=sample_letter_template,
        client_reference="letter_from_job",
        status=NOTIFICATION_RETURNED_LETTER,
        job=job,
        job_row_number=2,
        created_at=datetime.now(UTC) - timedelta(days=1),
        created_by_id=sample_letter_template.service.users[0].id,
    )
    create_returned_letter(
        service=sample_letter_template.service, reported_at=datetime.now(UTC), notification_id=letter_from_job.id
    )

    one_off_letter = create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_RETURNED_LETTER,
        created_at=datetime.now(UTC) - timedelta(days=2),
        created_by_id=sample_letter_template.service.users[0].id,
    )
    create_returned_letter(
        service=sample_letter_template.service, reported_at=datetime.utcnow(), notification_id=one_off_letter.id
    )

    api_key = create_api_key(service=sample_letter_template.service)
    api_letter = create_notification(
        template=sample_letter_template,
        client_reference="api_letter",
        status=NOTIFICATION_RETURNED_LETTER,
        created_at=datetime.now(UTC) - timedelta(days=3),
        api_key=api_key,
    )
    create_returned_letter(
        service=sample_letter_template.service, reported_at=datetime.utcnow(), notification_id=api_letter.id
    )

    precompiled_template = create_template(
        service=sample_letter_template.service, template_type="letter", hidden=True, template_name="hidden template"
    )
    precompiled_letter = create_notification_history(
        template=precompiled_template,
        api_key=api_key,
        client_reference="precompiled letter",
        created_at=datetime.now(UTC) - timedelta(days=4),
    )
    create_returned_letter(
        service=sample_letter_template.service, reported_at=datetime.utcnow(), notification_id=precompiled_letter.id
    )

    uploaded_letter = create_notification_history(
        template=precompiled_template,
        client_reference="filename.pdf",
        created_at=datetime.now(UTC) - timedelta(days=5),
        created_by_id=sample_letter_template.service.users[0].id,
    )
    create_returned_letter(
        service=sample_letter_template.service, reported_at=datetime.now(UTC), notification_id=uploaded_letter.id
    )

    # not included in results because wrong service
    not_included_in_results_template = create_template(
        service=create_service(service_name="not included in results"), template_type="letter"
    )
    letter_4 = create_notification_history(
        template=not_included_in_results_template, status=NOTIFICATION_RETURNED_LETTER
    )
    create_returned_letter(
        service=not_included_in_results_template.service, reported_at=datetime.now(UTC), notification_id=letter_4.id
    )

    # not included in results because wrong reported_at
    letter_5 = create_notification_history(
        template=precompiled_template,
        client_reference="filename.pdf",
        created_at=datetime.now(UTC) - timedelta(days=6),
        created_by_id=sample_letter_template.service.users[0].id,
    )
    create_returned_letter(
        service=sample_letter_template.service,
        reported_at=datetime.now(UTC) - timedelta(days=2),
        notification_id=letter_5.id,
    )

    # two "orphaned" letters
    create_returned_letter(
        service=sample_letter_template.service,
        reported_at=datetime.now(UTC),
        notification_id=uuid.uuid4(),
    )
    create_returned_letter(
        service=sample_letter_template.service,
        reported_at=datetime.now(UTC),
        notification_id=uuid.uuid4(),
    )

    # an "orphaned" letter for the wrong day
    create_returned_letter(
        service=sample_letter_template.service,
        reported_at=datetime.now(UTC) - timedelta(days=3),
        notification_id=uuid.uuid4(),
    )

    # an "orphaned" letter for the wrong service
    create_returned_letter(
        service=not_included_in_results_template.service,
        reported_at=datetime.now(UTC),
        notification_id=uuid.uuid4(),
    )

    response = api_client_request.get(
        sample_letter_template.service.id, "v2_returned_letters.get_returned_letters", report_date="2026-06-23"
    )

    assert response == {
        "returned_letters": [
            {
                "notification_id": str(letter_from_job.id),
                "reference": None,
                "report_date": "2026-06-23",
                "created_at": letter_from_job.created_at.strftime(DATETIME_FORMAT_NO_TIMEZONE),
                "email_address": letter_from_job.get_created_by_email_address(),
                "template_name": sample_letter_template.name,
                "template_id": str(sample_letter_template.id),
                "template_version": sample_letter_template.version,
                "spreadsheet_file_name": job.original_file_name,
                "spreadsheet_row_number": 4,
                "uploaded_letter_file_name": None,
            },
            {
                "notification_id": str(one_off_letter.id),
                "reference": None,
                "report_date": "2026-06-23",
                "created_at": one_off_letter.created_at.strftime(DATETIME_FORMAT_NO_TIMEZONE),
                "email_address": one_off_letter.get_created_by_email_address(),
                "template_name": sample_letter_template.name,
                "template_id": str(sample_letter_template.id),
                "template_version": sample_letter_template.version,
                "spreadsheet_file_name": None,
                "spreadsheet_row_number": None,
                "uploaded_letter_file_name": None,
            },
            {
                "notification_id": str(api_letter.id),
                "reference": api_letter.client_reference,
                "report_date": "2026-06-23",
                "created_at": api_letter.created_at.strftime(DATETIME_FORMAT_NO_TIMEZONE),
                "email_address": "API",
                "template_name": sample_letter_template.name,
                "template_id": str(sample_letter_template.id),
                "template_version": sample_letter_template.version,
                "spreadsheet_file_name": None,
                "spreadsheet_row_number": api_letter.job_row_number,
                "uploaded_letter_file_name": None,
            },
            {
                "notification_id": str(precompiled_letter.id),
                "reference": precompiled_letter.client_reference,
                "report_date": "2026-06-23",
                "created_at": precompiled_letter.created_at.strftime(DATETIME_FORMAT_NO_TIMEZONE),
                "email_address": "API",
                "template_name": "None",
                "template_id": "None",
                "template_version": None,
                "spreadsheet_file_name": None,
                "spreadsheet_row_number": precompiled_letter.job_row_number,
                "uploaded_letter_file_name": None,
            },
            {
                "notification_id": str(uploaded_letter.id),
                "reference": None,
                "report_date": "2026-06-23",
                "created_at": uploaded_letter.created_at.strftime(DATETIME_FORMAT_NO_TIMEZONE),
                "email_address": sample_letter_template.service.users[0].email_address,
                "template_name": "None",
                "template_id": "None",
                "template_version": None,
                "spreadsheet_file_name": None,
                "spreadsheet_row_number": uploaded_letter.job_row_number,
                "uploaded_letter_file_name": "filename.pdf",
            },
        ],
        "orphaned_count": 2,
    }


def test_v2_get_returned_letters_raises_error_for_non_live_keys(api_client_request, sample_service):
    api_client_request.get(
        sample_service.id,
        "v2_returned_letters.get_returned_letters",
        report_date="2026-06-23",
        _api_key_type="test",
        _expected_status=403,
    )
