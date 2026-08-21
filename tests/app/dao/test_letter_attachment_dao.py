import datetime

import pytest
from freezegun import freeze_time

from app import db
from app.dao.letter_attachment_dao import dao_get_archived_letter_attachments_older_than
from app.dao.templates_dao import dao_update_template
from app.models import LetterAttachment
from tests.app.db import create_archived_letter_attachment
from tests.utils import QueryRecorder


def _create_live_letter_attachment(template):
    attachment = LetterAttachment(
        created_by_id=template.created_by_id,
        original_filename="live.pdf",
        page_count=1,
        template=template,
    )
    dao_update_template(template)
    return attachment


@pytest.mark.parametrize(
    "session,expected_bind_key",
    (
        (db.session, None),
        (db.session_bulk, "bulk"),
    ),
)
def test_dao_get_archived_letter_attachments_older_than_filters_by_archived_before(
    sample_letter_template, session, expected_bind_key
):
    with freeze_time("2026-03-24 12:00:00"):
        within_deletion_window_archived_file = create_archived_letter_attachment(sample_letter_template)
    with freeze_time("2026-04-13 12:00:00"):
        create_archived_letter_attachment(sample_letter_template)
    _create_live_letter_attachment(sample_letter_template)

    with QueryRecorder() as query_recorder:
        results = dao_get_archived_letter_attachments_older_than(
            session=session,
            archived_before=datetime.datetime(2026, 4, 9, 12, 0),
            page_size=10,
        )

    assert len(results) == 1

    archived_file, service_id = results[0]

    assert archived_file.id == within_deletion_window_archived_file.id
    assert service_id == sample_letter_template.service_id
    assert {query_info.bind_key for query_info in query_recorder.queries} == {expected_bind_key}


@freeze_time("2026-04-23 12:00:00")
@pytest.mark.parametrize(
    "session,expected_bind_key",
    (
        (db.session, None),
        (db.session_bulk, "bulk"),
    ),
)
def test_dao_get_archived_letter_attachments_older_than_supports_page_size_and_keyset_pagination(
    sample_letter_template, session, expected_bind_key
):
    with freeze_time("2026-04-03 12:00:00"):
        archived_file_one = create_archived_letter_attachment(sample_letter_template)
    with freeze_time("2026-04-04 12:00:00"):
        archived_file_two = create_archived_letter_attachment(sample_letter_template)
    with freeze_time("2026-04-05 12:00:00"):
        archived_file_three = create_archived_letter_attachment(sample_letter_template)

    archived_before = datetime.datetime(2026, 4, 9, 12, 0)

    with QueryRecorder() as query_recorder:
        first_batch = dao_get_archived_letter_attachments_older_than(
            session=session,
            archived_before=archived_before,
            page_size=2,
        )
        second_batch = dao_get_archived_letter_attachments_older_than(
            session=session,
            archived_before=archived_before,
            page_size=2,
            older_than=first_batch[-1][0].id,
        )

    assert [row[0].id for row in first_batch] == [archived_file_one.id, archived_file_two.id]
    assert [row[0].id for row in second_batch] == [archived_file_three.id]
    assert {query_info.bind_key for query_info in query_recorder.queries} == {expected_bind_key}


@freeze_time("2026-04-23 12:00:00")
@pytest.mark.parametrize(
    "session,expected_bind_key",
    (
        (db.session, None),
        (db.session_bulk, "bulk"),
    ),
)
def test_dao_get_archived_letter_attachments_older_than_filters_by_archived_after(
    sample_letter_template, session, expected_bind_key
):
    with freeze_time("2026-03-24 12:00:00"):
        create_archived_letter_attachment(sample_letter_template)
    with freeze_time("2026-04-08 12:00:00"):
        in_window_archived_file = create_archived_letter_attachment(sample_letter_template)

    archived_before = datetime.datetime(2026, 4, 9, 12, 0)
    archived_after = datetime.datetime(2026, 4, 3, 12, 0)

    with QueryRecorder() as query_recorder:
        results = dao_get_archived_letter_attachments_older_than(
            session=session,
            archived_before=archived_before,
            archived_after=archived_after,
            page_size=10,
        )

    assert [archived_file.id for archived_file, _ in results] == [in_window_archived_file.id]
    assert {query_info.bind_key for query_info in query_recorder.queries} == {expected_bind_key}
