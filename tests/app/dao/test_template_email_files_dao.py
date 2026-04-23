import datetime

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import NoResultFound

from app import db
from app.constants import EMAIL_TYPE
from app.dao.template_email_files_dao import (
    dao_archive_template_email_file,
    dao_create_template_email_file,
    dao_get_archived_template_email_files_older_than,
    dao_get_template_email_file_by_id,
    dao_get_template_email_files_by_template_id,
    dao_update_template_email_file,
)
from app.dao.templates_dao import dao_update_template
from app.models import Template, TemplateEmailFile
from tests.app.db import create_template, create_template_email_file
from tests.utils import QueryRecorder


def test_create_template_email_files_dao(sample_email_template, sample_service):
    data = {
        "id": "d963f496-b075-4e13-90ae-1f009feddbc6",
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "template_id": str(sample_email_template.id),
        "template_version": int(sample_email_template.version),
        "created_by_id": str(sample_service.users[0].id),
        "pending": False,
    }
    template_email_file = TemplateEmailFile(**data)
    dao_create_template_email_file(template_email_file)
    template_email_file = TemplateEmailFile.query.filter(
        TemplateEmailFile.template_id == str(sample_email_template.id)
    ).one()
    assert str(template_email_file.id) == "d963f496-b075-4e13-90ae-1f009feddbc6"
    assert template_email_file.filename == "example.pdf"
    assert template_email_file.link_text == "click this link!"
    assert template_email_file.retention_period == 90
    assert template_email_file.validate_users_email
    assert template_email_file.version == 1
    assert template_email_file.created_by_id == sample_service.users[0].id
    assert not template_email_file.pending


def test_dao_get_template_email_file_by_id(sample_template_email_file_not_pending, sample_service):
    # additional file for new template, get method shouldn't return this file
    new_template = create_template(service=sample_service, template_type=EMAIL_TYPE, template_name="template_two")
    create_template_email_file(
        new_template.id,
        created_by_id=sample_service.users[0].id,
        filename="file_two.pdf",
        link_text="click this other link",
    )
    template_email_file_fetched = dao_get_template_email_file_by_id(str(sample_template_email_file_not_pending.id))
    assert template_email_file_fetched.id == sample_template_email_file_not_pending.id
    assert template_email_file_fetched.filename == sample_template_email_file_not_pending.filename
    assert template_email_file_fetched.link_text == sample_template_email_file_not_pending.link_text
    assert template_email_file_fetched.retention_period == sample_template_email_file_not_pending.retention_period
    assert (
        template_email_file_fetched.validate_users_email == sample_template_email_file_not_pending.validate_users_email
    )
    assert template_email_file_fetched.template_version == sample_template_email_file_not_pending.template_version
    assert template_email_file_fetched.created_by_id == sample_template_email_file_not_pending.created_by_id
    assert not template_email_file_fetched.pending


def test_dao_get_template_email_file_by_id_returns_none_when_not_found():
    with pytest.raises(NoResultFound):
        dao_get_template_email_file_by_id("2117b6ab-0219-4bfa-aaa4-a3248dafa1a0")


def test_dao_get_template_email_files_by_template_id(
    sample_template_email_file_not_pending, sample_email_template, sample_service
):
    # should be fetched
    file_two = create_template_email_file(
        filename="example_two",
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
    )
    # shouldn't be fetched
    file_three = create_template_email_file(
        filename="example_two",
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
    )
    file_three.archived_at = datetime.datetime.now()
    file_three.archived_by_id = sample_email_template.created_by_id

    template_two = create_template(service=sample_service, template_type=EMAIL_TYPE, template_name="other_template")
    # shouldn't be fetched
    create_template_email_file(
        filename="example_three", template_id=template_two.id, created_by_id=template_two.created_by_id
    )

    fetched_file_list = dao_get_template_email_files_by_template_id(
        str(sample_template_email_file_not_pending.template_id)
    )

    assert len(fetched_file_list) == 2

    assert sample_template_email_file_not_pending in fetched_file_list
    assert file_two in fetched_file_list


def test_dao_get_template_email_files_by_template_id_does_not_return_archived_file(
    sample_template_email_file_not_pending,
):
    sample_template_email_file_not_pending.archived_at = datetime.datetime.now()
    sample_template_email_file_not_pending.archived_by_id = sample_template_email_file_not_pending.created_by_id
    fetched_file_list = dao_get_template_email_files_by_template_id(
        str(sample_template_email_file_not_pending.template_id)
    )
    assert not fetched_file_list


def test_dao_get_template_email_files_by_template_id_and_version_does_not_return_archived_file(
    sample_template_email_file_not_pending,
):
    sample_template_email_file_not_pending.archived_at = datetime.datetime.now()
    sample_template_email_file_not_pending.archived_by_id = sample_template_email_file_not_pending.created_by_id
    dao_update_template_email_file(sample_template_email_file_not_pending)
    fetched_file_latest = dao_get_template_email_files_by_template_id(
        str(sample_template_email_file_not_pending.template_id), template_version=3
    )
    assert not fetched_file_latest
    fetched_file_latest = dao_get_template_email_files_by_template_id(
        str(sample_template_email_file_not_pending.template_id)
    )
    assert not fetched_file_latest


def test_dao_get_template_email_files_by_template_id_historical(
    sample_email_template, sample_template_email_file_not_pending
):
    sample_email_template.updated_at = datetime.datetime.utcnow()
    dao_update_template(sample_email_template)
    # sample_email_template.updated_at = datetime.datetime.utcnow()
    # dao_update_template(sample_email_template)
    sample_template_email_file_not_pending.retention_period = 20
    dao_update_template_email_file(sample_template_email_file_not_pending)
    assert sample_email_template.version == 3
    template_version_to_get = 1
    template_email_file_fetched = dao_get_template_email_files_by_template_id(
        sample_email_template.id, template_version=template_version_to_get
    )[0]
    assert template_email_file_fetched.id == sample_template_email_file_not_pending.id
    assert template_email_file_fetched.filename == sample_template_email_file_not_pending.filename
    assert template_email_file_fetched.link_text == sample_template_email_file_not_pending.link_text
    assert template_email_file_fetched.retention_period == 90  # we want the initial retention period for historical
    assert (
        template_email_file_fetched.validate_users_email == sample_template_email_file_not_pending.validate_users_email
    )
    assert template_email_file_fetched.template_version == template_version_to_get
    assert template_email_file_fetched.created_by_id == sample_template_email_file_not_pending.created_by_id


def test_dao_update_template_email_file(sample_email_template, sample_template_email_file_not_pending):
    sample_template_email_file_not_pending.link_text = "click this new link"
    sample_template_email_file_not_pending.retention_period = 30
    dao_update_template_email_file(sample_template_email_file_not_pending)
    fetched_template_email_file = TemplateEmailFile.query.get(sample_template_email_file_not_pending.id)
    fetched_template = Template.query.get(sample_email_template.id)
    assert fetched_template_email_file.version == 2
    assert fetched_template_email_file.template_version == 2
    assert fetched_template_email_file.link_text == "click this new link"
    assert fetched_template_email_file.retention_period == 30
    assert fetched_template.version == 2


@freeze_time("2025-07-30 16:06:04.000000")
def test_dao_archive_template_email_file(sample_email_template, sample_template_email_file_not_pending):
    dao_archive_template_email_file(
        sample_template_email_file_not_pending,
        sample_template_email_file_not_pending.created_by_id,
        template_version=sample_email_template.version + 1,
    )

    fetched_email_file = TemplateEmailFile.query.get(sample_template_email_file_not_pending.id)
    assert fetched_email_file.version == 2
    assert fetched_email_file.archived_at == datetime.datetime(2025, 7, 30, 16, 6, 4)
    assert fetched_email_file.archived_by_id == sample_template_email_file_not_pending.created_by_id
    assert fetched_email_file.template_version == sample_email_template.version + 1

    fetched_latest_history = TemplateEmailFile.query.filter_by(
        id=sample_template_email_file_not_pending.id, version=2
    ).one()
    assert fetched_latest_history.version == 2
    assert fetched_latest_history.archived_at == datetime.datetime(2025, 7, 30, 16, 6, 4)
    assert fetched_latest_history.archived_by_id == sample_template_email_file_not_pending.created_by_id
    assert fetched_latest_history.template_version == sample_email_template.version + 1


@freeze_time("2026-04-23 12:00:00")
@pytest.mark.parametrize(
    "session,expected_bind_key",
    (
        (db.session, None),
        (db.session_bulk, "bulk"),
    ),
)
def test_dao_get_archived_template_email_files_older_than_filters_by_archived_to(
    sample_email_template, session, expected_bind_key
):
    old_archived_file = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="old.pdf",
    )
    recent_archived_file = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="recent.pdf",
    )
    unarchived_file = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="live.pdf",
    )

    old_archived_file.archived_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
    old_archived_file.archived_by_id = sample_email_template.created_by_id
    recent_archived_file.archived_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)
    recent_archived_file.archived_by_id = sample_email_template.created_by_id
    unarchived_file.archived_at = None

    archived_to = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=14)
    db.session.commit()

    with QueryRecorder() as query_recorder:
        results = dao_get_archived_template_email_files_older_than(
            session=session,
            archived_to=archived_to,
            limit=10,
            offset=0,
        )

    assert len(results) == 1
    archived_file, service_id = results[0]
    assert archived_file.id == old_archived_file.id
    assert service_id == sample_email_template.service_id
    assert {query_info.bind_key for query_info in query_recorder.queries} == {expected_bind_key}


@freeze_time("2026-04-23 12:00:00")
@pytest.mark.parametrize(
    "session,expected_bind_key",
    (
        (db.session, None),
        (db.session_bulk, "bulk"),
    ),
)
def test_dao_get_archived_template_email_files_older_than_supports_limit_and_offset(
    sample_email_template, session, expected_bind_key
):
    archived_file_one = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="one.pdf",
    )
    archived_file_two = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="two.pdf",
    )
    archived_file_three = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="three.pdf",
    )

    now = datetime.datetime.now(datetime.UTC)
    archived_file_one.archived_at = now - datetime.timedelta(days=20)
    archived_file_two.archived_at = now - datetime.timedelta(days=19)
    archived_file_three.archived_at = now - datetime.timedelta(days=18)
    archived_file_one.archived_by_id = sample_email_template.created_by_id
    archived_file_two.archived_by_id = sample_email_template.created_by_id
    archived_file_three.archived_by_id = sample_email_template.created_by_id

    archived_to = now - datetime.timedelta(days=14)
    db.session.commit()

    with QueryRecorder() as query_recorder:
        first_batch = dao_get_archived_template_email_files_older_than(
            session=session,
            archived_to=archived_to,
            limit=2,
            offset=0,
        )
        second_batch = dao_get_archived_template_email_files_older_than(
            session=session,
            archived_to=archived_to,
            limit=2,
            offset=2,
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
def test_dao_get_archived_template_email_files_older_than_filters_by_archived_from(
    sample_email_template, session, expected_bind_key
):
    old_archived_file = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="old-window.pdf",
    )
    in_window_archived_file = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="in-window.pdf",
    )

    now = datetime.datetime.now(datetime.UTC)
    old_archived_file.archived_at = now - datetime.timedelta(days=30)
    old_archived_file.archived_by_id = sample_email_template.created_by_id
    in_window_archived_file.archived_at = now - datetime.timedelta(days=15)
    in_window_archived_file.archived_by_id = sample_email_template.created_by_id

    archived_to = now - datetime.timedelta(days=14)
    archived_from = now - datetime.timedelta(days=20)
    db.session.commit()

    with QueryRecorder() as query_recorder:
        results = dao_get_archived_template_email_files_older_than(
            session=session,
            archived_to=archived_to,
            archived_from=archived_from,
            limit=10,
            offset=0,
        )

    assert [archived_file.id for archived_file, _ in results] == [in_window_archived_file.id]
    assert {query_info.bind_key for query_info in query_recorder.queries} == {expected_bind_key}


@freeze_time("2026-04-23 12:00:00")
@pytest.mark.parametrize(
    "session,expected_bind_key",
    (
        (db.session, None),
        (db.session_bulk, "bulk"),
    ),
)
def test_dao_get_archived_template_email_files_older_than_archived_from_does_not_bypass_retention(
    sample_email_template, session, expected_bind_key
):
    old_archived_file = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="old-eligible.pdf",
    )
    not_old_enough_file = create_template_email_file(
        template_id=sample_email_template.id,
        created_by_id=sample_email_template.created_by_id,
        filename="not-old-enough.pdf",
    )

    now = datetime.datetime.now(datetime.UTC)
    old_archived_file.archived_at = now - datetime.timedelta(days=30)
    old_archived_file.archived_by_id = sample_email_template.created_by_id
    # archived_from should never allow this one through because retention is 14 days.
    not_old_enough_file.archived_at = now - datetime.timedelta(days=10)
    not_old_enough_file.archived_by_id = sample_email_template.created_by_id

    archived_to = now - datetime.timedelta(days=14)
    archived_from = now - datetime.timedelta(days=60)
    db.session.commit()

    with QueryRecorder() as query_recorder:
        results = dao_get_archived_template_email_files_older_than(
            session=session,
            archived_to=archived_to,
            archived_from=archived_from,
            limit=10,
            offset=0,
        )

    assert [archived_file.id for archived_file, _ in results] == [old_archived_file.id]
    assert {query_info.bind_key for query_info in query_recorder.queries} == {expected_bind_key}
