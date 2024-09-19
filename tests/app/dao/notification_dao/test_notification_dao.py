import uuid
from datetime import date, datetime, timedelta
from functools import partial

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound

from app.constants import (
    JOB_STATUS_IN_PROGRESS,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_STATUS_TYPES,
    NOTIFICATION_STATUS_TYPES_FAILED,
    NOTIFICATION_TEMPORARY_FAILURE,
    SMS_TYPE,
)
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_delete_notifications_by_id,
    dao_get_last_notification_added_for_job_id,
    dao_get_letters_and_sheets_volume_by_postage,
    dao_get_letters_to_be_printed,
    dao_get_notification_by_reference,
    dao_get_notification_count_for_job_id,
    dao_get_notification_or_history_by_id,
    dao_get_notification_or_history_by_reference,
    dao_get_notifications_by_recipient_or_reference,
    dao_record_letter_despatched_on_by_id,
    dao_timeout_notifications,
    dao_update_notification,
    dao_update_notifications_by_reference,
    get_notification_by_id,
    get_notification_with_personalisation,
    get_notifications_for_job,
    get_notifications_for_service,
    get_service_ids_with_notifications_on_date,
    is_delivery_slow_for_providers,
    notifications_not_yet_sent,
    update_notification_status_by_id,
)
from app.models import Job, LetterCostThreshold, Notification, NotificationHistory, NotificationLetterDespatch
from tests.app.db import (
    create_ft_notification_status,
    create_job,
    create_notification,
    create_notification_history,
    create_service,
    create_template,
)


def test_should_by_able_to_update_status_by_id(sample_template, sample_job, mmg_provider):
    with freeze_time("2000-01-01 12:00:00"):
        data = _notification_json(sample_template, job_id=sample_job.id, status="sending")
        notification = Notification(**data)
        dao_create_notification(notification)
        assert notification.status == "sending"

    assert Notification.query.get(notification.id).status == "sending"

    with freeze_time("2000-01-02 12:00:00"):
        updated = update_notification_status_by_id(notification.id, "delivered")

    assert updated.status == "delivered"
    assert updated.updated_at == datetime(2000, 1, 2, 12, 0, 0)
    assert Notification.query.get(notification.id).status == "delivered"
    assert notification.updated_at == datetime(2000, 1, 2, 12, 0, 0)
    assert notification.status == "delivered"


def test_should_not_update_status_by_id_if_not_sending_and_does_not_update_job(sample_job):
    notification = create_notification(template=sample_job.template, status="delivered", job=sample_job)
    assert Notification.query.get(notification.id).status == "delivered"
    assert not update_notification_status_by_id(notification.id, "failed")
    assert Notification.query.get(notification.id).status == "delivered"
    assert sample_job == Job.query.get(notification.job_id)


def test_should_update_status_by_id_if_created(sample_template, sample_notification):
    assert Notification.query.get(sample_notification.id).status == "created"
    updated = update_notification_status_by_id(sample_notification.id, "failed")
    assert Notification.query.get(sample_notification.id).status == "failed"
    assert updated.status == "failed"


def test_should_update_status_by_id_if_pending_virus_check(sample_letter_template):
    notification = create_notification(template=sample_letter_template, status="pending-virus-check")
    assert Notification.query.get(notification.id).status == "pending-virus-check"
    updated = update_notification_status_by_id(notification.id, "cancelled")
    assert Notification.query.get(notification.id).status == "cancelled"
    assert updated.status == "cancelled"


def test_should_update_status_of_international_letter_to_cancelled(sample_letter_template):
    notification = create_notification(
        template=sample_letter_template,
        international=True,
        postage="europe",
    )
    assert Notification.query.get(notification.id).international is True
    update_notification_status_by_id(notification.id, "cancelled")
    assert Notification.query.get(notification.id).status == "cancelled"


def test_should_update_status_by_id_and_set_sent_by(sample_template):
    notification = create_notification(template=sample_template, status="sending")

    updated = update_notification_status_by_id(notification.id, "delivered", sent_by="mmg")
    assert updated.status == "delivered"
    assert updated.sent_by == "mmg"


def test_should_not_update_status_by_id_if_sent_to_country_with_unknown_delivery_receipts(sample_template):
    notification = create_notification(
        sample_template,
        status=NOTIFICATION_SENT,
        international=True,
        phone_prefix="249",  # sudan has no delivery receipts (or at least, that we know about)
    )

    res = update_notification_status_by_id(notification.id, "delivered")

    assert res is None
    assert notification.status == NOTIFICATION_SENT


def test_should_not_update_status_by_id_if_sent_to_country_with_carrier_delivery_receipts(sample_template):
    notification = create_notification(
        sample_template,
        status=NOTIFICATION_SENT,
        international=True,
        phone_prefix="1",  # americans only have carrier delivery receipts
    )

    res = update_notification_status_by_id(notification.id, "delivered")

    assert res is None
    assert notification.status == NOTIFICATION_SENT


def test_should_not_update_status_by_id_if_sent_to_country_with_delivery_receipts(sample_template):
    notification = create_notification(
        sample_template,
        status=NOTIFICATION_SENT,
        international=True,
        phone_prefix="7",  # russians have full delivery receipts
    )

    res = update_notification_status_by_id(notification.id, "delivered")

    assert res == notification
    assert notification.status == NOTIFICATION_DELIVERED


def test_should_by_able_to_update_status_by_id_from_pending_to_delivered(sample_template, sample_job):
    notification = create_notification(template=sample_template, job=sample_job, status="sending")

    assert update_notification_status_by_id(notification_id=notification.id, status="pending")
    assert Notification.query.get(notification.id).status == "pending"

    assert update_notification_status_by_id(notification.id, "delivered")
    assert Notification.query.get(notification.id).status == "delivered"


def test_should_by_able_to_update_status_by_id_from_pending_to_temporary_failure(sample_template, sample_job):
    notification = create_notification(template=sample_template, job=sample_job, status="sending", sent_by="firetext")

    assert update_notification_status_by_id(notification_id=notification.id, status="pending")
    assert Notification.query.get(notification.id).status == "pending"

    assert update_notification_status_by_id(notification.id, status="permanent-failure")

    assert Notification.query.get(notification.id).status == "temporary-failure"


def test_should_by_able_to_update_status_by_id_from_sending_to_permanent_failure(sample_template, sample_job):
    data = _notification_json(sample_template, job_id=sample_job.id, status="sending")
    notification = Notification(**data)
    dao_create_notification(notification)
    assert Notification.query.get(notification.id).status == "sending"

    assert update_notification_status_by_id(notification.id, status="permanent-failure")
    assert Notification.query.get(notification.id).status == "permanent-failure"


def test_should_return_zero_count_if_no_notification_with_id():
    assert not update_notification_status_by_id(str(uuid.uuid4()), "delivered")


def test_create_notification_creates_notification_with_personalisation(sample_template_with_placeholders, sample_job):
    assert Notification.query.count() == 0

    data = create_notification(
        template=sample_template_with_placeholders, job=sample_job, personalisation={"name": "Jo"}, status="created"
    )

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data.to == notification_from_db.to
    assert data.job_id == notification_from_db.job_id
    assert data.service == notification_from_db.service
    assert data.template == notification_from_db.template
    assert data.template_version == notification_from_db.template_version
    assert data.created_at == notification_from_db.created_at
    assert notification_from_db.status == "created"
    assert {"name": "Jo"} == notification_from_db.personalisation


def test_save_notification_creates_sms(sample_template, sample_job):
    assert Notification.query.count() == 0

    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data["to"] == notification_from_db.to
    assert data["job_id"] == notification_from_db.job_id
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == "created"


def test_save_notification_and_create_email(sample_email_template, sample_job):
    assert Notification.query.count() == 0

    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data["to"] == notification_from_db.to
    assert data["job_id"] == notification_from_db.job_id
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == "created"


def test_save_notification(sample_email_template, sample_job):
    assert Notification.query.count() == 0
    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    dao_create_notification(notification_1)

    assert Notification.query.count() == 1

    dao_create_notification(notification_2)

    assert Notification.query.count() == 2


def test_save_notification_does_not_creates_history(sample_email_template, sample_job):
    assert Notification.query.count() == 0
    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    dao_create_notification(notification_1)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0


def test_not_save_notification_and_not_create_stats_on_commit_error(sample_template, sample_job, mmg_provider):
    random_id = str(uuid.uuid4())

    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=random_id)

    notification = Notification(**data)
    with pytest.raises(SQLAlchemyError):
        dao_create_notification(notification)

    assert Notification.query.count() == 0
    assert Job.query.get(sample_job.id).notifications_sent == 0


def test_save_notification_and_increment_job(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data["to"] == notification_from_db.to
    assert data["job_id"] == notification_from_db.job_id
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == "created"

    notification_2 = Notification(**data)
    dao_create_notification(notification_2)
    assert Notification.query.count() == 2


def test_save_notification_and_increment_correct_job(sample_template, mmg_provider):
    job_1 = create_job(sample_template)
    job_2 = create_job(sample_template)

    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=job_1.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data["to"] == notification_from_db.to
    assert data["job_id"] == notification_from_db.job_id
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == "created"
    assert job_1.id != job_2.id


def test_save_notification_with_no_job(sample_template, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data["to"] == notification_from_db.to
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == "created"


@pytest.mark.parametrize(
    "template_type, unsubscribe_link",
    [
        ("email", None),
        ("email", "https://unsub.com"),
        pytest.param("sms", "https://unsub.com", marks=pytest.mark.xfail(raises=IntegrityError)),
    ],
)
def test_dao_create_notification_with_unsubscribe_link(
    sample_template, sample_email_template, template_type, unsubscribe_link
):
    template_data = {"email": sample_email_template, "sms": sample_template}
    notification_data = _notification_json(template_data[template_type])
    notification_data["unsubscribe_link"] = unsubscribe_link
    notification = Notification(**notification_data)

    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.unsubscribe_link == unsubscribe_link


def test_get_notification_with_personalisation_by_id(sample_template):
    notification = create_notification(template=sample_template, status="created")
    notification_from_db = get_notification_with_personalisation(
        sample_template.service.id, notification.id, key_type=None
    )
    assert notification == notification_from_db


def test_get_notification_by_id_when_notification_exists(sample_notification):
    notification_from_db = get_notification_by_id(sample_notification.id)

    assert sample_notification == notification_from_db


def test_get_notification_by_id_when_notification_does_not_exist(notify_db_session, fake_uuid):
    notification_from_db = get_notification_by_id(fake_uuid)

    assert notification_from_db is None


def test_get_notification_by_id_when_notification_exists_for_different_service(sample_notification):
    another_service = create_service(service_name="Another service")

    with pytest.raises(NoResultFound):
        get_notification_by_id(sample_notification.id, another_service.id, _raise=True)


def test_get_notifications_by_reference(sample_template):
    client_reference = "some-client-ref"
    assert len(Notification.query.all()) == 0
    create_notification(sample_template, client_reference=client_reference)
    create_notification(sample_template, client_reference=client_reference)
    create_notification(sample_template, client_reference="other-ref")
    all_notifications = get_notifications_for_service(
        sample_template.service_id, client_reference=client_reference
    ).items
    assert len(all_notifications) == 2


def test_save_notification_no_job_id(sample_template):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data["to"] == notification_from_db.to
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert notification_from_db.status == "created"
    assert data.get("job_id") is None


def test_get_all_notifications_for_job(sample_job):
    for _ in range(5):
        try:
            create_notification(template=sample_job.template, job=sample_job)
        except IntegrityError:
            pass

    notifications_from_db = get_notifications_for_job(sample_job.service.id, sample_job.id).items
    assert len(notifications_from_db) == 5


def test_get_all_notifications_for_job_by_status(sample_job):
    notifications = partial(get_notifications_for_job, sample_job.service.id, sample_job.id)

    for status in NOTIFICATION_STATUS_TYPES:
        create_notification(template=sample_job.template, job=sample_job, status=status)

    assert len(notifications().items) == len(NOTIFICATION_STATUS_TYPES)

    for status in NOTIFICATION_STATUS_TYPES:
        if status == "failed":
            assert len(notifications(filter_dict={"status": status}).items) == len(NOTIFICATION_STATUS_TYPES_FAILED)
        else:
            assert len(notifications(filter_dict={"status": status}).items) == 1

    assert len(notifications(filter_dict={"status": NOTIFICATION_STATUS_TYPES[:3]}).items) == 3


def test_dao_get_notification_count_for_job_id(notify_db_session):
    service = create_service()
    template = create_template(service)
    job = create_job(template, notification_count=3)
    for _ in range(3):
        create_notification(job=job)

    create_notification(template)

    assert dao_get_notification_count_for_job_id(job_id=job.id) == 3


def test_dao_get_notification_count_for_job_id_returns_zero_for_no_notifications_for_job(notify_db_session):
    service = create_service()
    template = create_template(service)
    job = create_job(template, notification_count=3)
    create_notification(template)

    assert dao_get_notification_count_for_job_id(job_id=job.id) == 0


def test_update_notification_sets_status(sample_notification):
    assert sample_notification.status == "created"
    sample_notification.status = "failed"
    dao_update_notification(sample_notification)
    notification_from_db = Notification.query.get(sample_notification.id)
    assert notification_from_db.status == "failed"


@freeze_time("2016-01-10")
def test_should_limit_notifications_return_by_day_limit_plus_one(sample_template):
    assert len(Notification.query.all()) == 0

    # create one notification a day between 1st and 9th
    for i in range(1, 11):
        past_date = f"2016-01-{i:02d}"
        with freeze_time(past_date):
            create_notification(sample_template, created_at=datetime.utcnow(), status="failed")

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 10

    all_notifications = get_notifications_for_service(sample_template.service_id, limit_days=10).items
    assert len(all_notifications) == 10

    all_notifications = get_notifications_for_service(sample_template.service_id, limit_days=1).items
    assert len(all_notifications) == 2


def test_creating_notification_does_not_add_notification_history(sample_template):
    create_notification(template=sample_template)
    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0


def test_should_delete_notification_for_id(sample_template):
    notification = create_notification(template=sample_template)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0

    dao_delete_notifications_by_id(notification.id)

    assert Notification.query.count() == 0


def test_should_delete_only_notification_with_id(sample_template):
    notification_1 = create_notification(template=sample_template)
    notification_2 = create_notification(template=sample_template)
    assert Notification.query.count() == 2

    dao_delete_notifications_by_id(notification_1.id)

    assert Notification.query.count() == 1
    assert Notification.query.first().id == notification_2.id


def test_should_delete_no_notifications_if_no_matching_ids(sample_template):
    create_notification(template=sample_template)
    assert Notification.query.count() == 1

    dao_delete_notifications_by_id(uuid.uuid4())

    assert Notification.query.count() == 1


def _notification_json(sample_template, job_id=None, id=None, status=None):
    data = {
        "to": "+44709123456",
        "service": sample_template.service,
        "service_id": sample_template.service.id,
        "template_id": sample_template.id,
        "template_version": sample_template.version,
        "created_at": datetime.utcnow(),
        "billable_units": 1,
        "notification_type": sample_template.template_type,
        "key_type": KEY_TYPE_NORMAL,
    }
    if job_id:
        data.update({"job_id": job_id})
    if id:
        data.update({"id": id})
    if status:
        data.update({"status": status})
    return data


def test_dao_timeout_notifications(sample_template):
    with freeze_time(datetime.utcnow() - timedelta(minutes=2)):
        created = create_notification(sample_template, status="created")
        sending = create_notification(sample_template, status="sending")
        pending = create_notification(sample_template, status="pending")
        delivered = create_notification(sample_template, status="delivered")

    temporary_failure_notifications = dao_timeout_notifications(datetime.utcnow())

    assert len(temporary_failure_notifications) == 2
    assert Notification.query.get(created.id).status == "created"
    assert Notification.query.get(sending.id).status == "temporary-failure"
    assert Notification.query.get(pending.id).status == "temporary-failure"
    assert Notification.query.get(delivered.id).status == "delivered"


def test_dao_timeout_notifications_only_updates_for_older_notifications(sample_template):
    with freeze_time(datetime.utcnow() + timedelta(minutes=10)):
        sending = create_notification(sample_template, status="sending")
        pending = create_notification(sample_template, status="pending")

    temporary_failure_notifications = dao_timeout_notifications(datetime.utcnow())

    assert len(temporary_failure_notifications) == 0
    assert Notification.query.get(sending.id).status == "sending"
    assert Notification.query.get(pending.id).status == "pending"


def test_dao_timeout_notifications_doesnt_affect_letters(sample_letter_template):
    with freeze_time(datetime.utcnow() - timedelta(minutes=2)):
        sending = create_notification(sample_letter_template, status="sending")
        pending = create_notification(sample_letter_template, status="pending")

    temporary_failure_notifications = dao_timeout_notifications(datetime.utcnow())

    assert len(temporary_failure_notifications) == 0
    assert Notification.query.get(sending.id).status == "sending"
    assert Notification.query.get(pending.id).status == "pending"


def test_should_return_notifications_excluding_jobs_by_default(sample_template, sample_job, sample_api_key):
    create_notification(sample_template, job=sample_job)
    without_job = create_notification(sample_template, api_key=sample_api_key)

    include_jobs = get_notifications_for_service(sample_template.service_id, include_jobs=True).items
    assert len(include_jobs) == 2

    exclude_jobs_by_default = get_notifications_for_service(sample_template.service_id).items
    assert len(exclude_jobs_by_default) == 1
    assert exclude_jobs_by_default[0].id == without_job.id

    exclude_jobs_manually = get_notifications_for_service(sample_template.service_id, include_jobs=False).items
    assert len(exclude_jobs_manually) == 1
    assert exclude_jobs_manually[0].id == without_job.id


def test_should_return_notifications_including_one_offs_by_default(sample_user, sample_template):
    create_notification(sample_template, one_off=True, created_by_id=sample_user.id)
    not_one_off = create_notification(sample_template)

    exclude_one_offs = get_notifications_for_service(sample_template.service_id, include_one_off=False).items
    assert len(exclude_one_offs) == 1
    assert exclude_one_offs[0].id == not_one_off.id

    include_one_offs_manually = get_notifications_for_service(sample_template.service_id, include_one_off=True).items
    assert len(include_one_offs_manually) == 2

    include_one_offs_by_default = get_notifications_for_service(sample_template.service_id).items
    assert len(include_one_offs_by_default) == 2


def test_should_not_count_pages_when_given_a_flag(sample_user, sample_template):
    create_notification(sample_template)
    notification = create_notification(sample_template)

    pagination = get_notifications_for_service(sample_template.service_id, count_pages=False, page_size=1)
    assert len(pagination.items) == 1
    assert pagination.total is None
    assert pagination.items[0].id == notification.id


def test_get_notifications_created_by_api_or_csv_are_returned_correctly_excluding_test_key_notifications(
    notify_db_session, sample_service, sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(template=sample_job.template, created_at=datetime.utcnow(), job=sample_job)
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 4

    # returns all real API derived notifications
    all_notifications = get_notifications_for_service(sample_service.id).items
    assert len(all_notifications) == 2

    # returns all API derived notifications, including those created with test key
    all_notifications = get_notifications_for_service(sample_service.id, include_from_test_key=True).items
    assert len(all_notifications) == 3

    # all real notifications including jobs
    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, include_jobs=True).items
    assert len(all_notifications) == 3


def test_get_notifications_with_a_live_api_key_type(
    sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(template=sample_job.template, created_at=datetime.utcnow(), job=sample_job)
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 4

    # only those created with normal API key, no jobs
    all_notifications = get_notifications_for_service(
        sample_job.service.id, limit_days=1, key_type=KEY_TYPE_NORMAL
    ).items
    assert len(all_notifications) == 1

    # only those created with normal API key, with jobs
    all_notifications = get_notifications_for_service(
        sample_job.service.id, limit_days=1, include_jobs=True, key_type=KEY_TYPE_NORMAL
    ).items
    assert len(all_notifications) == 2


def test_get_notifications_with_a_test_api_key_type(
    sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(template=sample_job.template, created_at=datetime.utcnow(), job=sample_job)
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    # only those created with test API key, no jobs
    all_notifications = get_notifications_for_service(sample_job.service_id, limit_days=1, key_type=KEY_TYPE_TEST).items
    assert len(all_notifications) == 1

    # only those created with test API key, no jobs, even when requested
    all_notifications = get_notifications_for_service(
        sample_job.service_id, limit_days=1, include_jobs=True, key_type=KEY_TYPE_TEST
    ).items
    assert len(all_notifications) == 1


def test_get_notifications_with_a_team_api_key_type(
    sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(template=sample_job.template, created_at=datetime.utcnow(), job=sample_job)
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    # only those created with team API key, no jobs
    all_notifications = get_notifications_for_service(sample_job.service_id, limit_days=1, key_type=KEY_TYPE_TEAM).items
    assert len(all_notifications) == 1

    # only those created with team API key, no jobs, even when requested
    all_notifications = get_notifications_for_service(
        sample_job.service_id, limit_days=1, include_jobs=True, key_type=KEY_TYPE_TEAM
    ).items
    assert len(all_notifications) == 1


def test_should_exclude_test_key_notifications_by_default(
    sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(template=sample_job.template, created_at=datetime.utcnow(), job=sample_job)

    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=datetime.utcnow(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 4

    all_notifications = get_notifications_for_service(sample_job.service_id, limit_days=1).items
    assert len(all_notifications) == 2

    all_notifications = get_notifications_for_service(sample_job.service_id, limit_days=1, include_jobs=True).items
    assert len(all_notifications) == 3

    all_notifications = get_notifications_for_service(sample_job.service_id, limit_days=1, key_type=KEY_TYPE_TEST).items
    assert len(all_notifications) == 1


@pytest.mark.parametrize(
    "normal_sending,slow_sending,normal_delivered,slow_delivered,threshold,expected_result",
    [
        (0, 0, 0, 0, 0.1, False),
        (1, 0, 0, 0, 0.1, False),
        (1, 1, 0, 0, 0.1, True),
        (0, 0, 1, 1, 0.1, True),
        (1, 1, 1, 1, 0.5, True),
        (1, 1, 1, 1, 0.6, False),
        (45, 5, 45, 5, 0.1, True),
    ],
)
@freeze_time("2018-12-04 12:00:00.000000")
def test_is_delivery_slow_for_providers(
    notify_db_session,
    sample_template,
    normal_sending,
    slow_sending,
    normal_delivered,
    slow_delivered,
    threshold,
    expected_result,
):
    normal_notification = partial(
        create_notification, template=sample_template, sent_by="mmg", sent_at=datetime.now(), updated_at=datetime.now()
    )

    slow_notification = partial(
        create_notification,
        template=sample_template,
        sent_by="mmg",
        sent_at=datetime.now() - timedelta(minutes=5),
        updated_at=datetime.now(),
    )

    for _ in range(normal_sending):
        normal_notification(status="sending")
    for _ in range(slow_sending):
        slow_notification(status="sending")
    for _ in range(normal_delivered):
        normal_notification(status="delivered")
    for _ in range(slow_delivered):
        slow_notification(status="delivered")

    result = is_delivery_slow_for_providers(10, 5, threshold)
    assert result == {"firetext": False, "mmg": expected_result}


@pytest.mark.parametrize(
    "options,expected_result",
    [
        ({"status": NOTIFICATION_DELIVERED, "sent_by": "mmg"}, True),
        ({"status": NOTIFICATION_PENDING, "sent_by": "mmg"}, True),
        ({"status": NOTIFICATION_SENDING, "sent_by": "mmg"}, True),
        ({"status": NOTIFICATION_TEMPORARY_FAILURE, "sent_by": "mmg"}, False),
        ({"status": NOTIFICATION_DELIVERED, "sent_by": "mmg", "sent_at": None}, False),
        ({"status": NOTIFICATION_DELIVERED, "sent_by": "mmg", "key_type": KEY_TYPE_TEST}, False),
        ({"status": NOTIFICATION_SENDING, "sent_by": "firetext"}, False),
        ({"status": NOTIFICATION_DELIVERED, "sent_by": "firetext"}, False),
    ],
)
@freeze_time("2018-12-04 12:00:00.000000")
def test_delivery_is_delivery_slow_for_providers_filters_out_notifications_it_should_not_count(
    notify_db_session, sample_template, options, expected_result
):
    create_slow_notification_with = {
        "template": sample_template,
        "sent_at": datetime.now() - timedelta(minutes=5),
        "updated_at": datetime.now(),
    }
    create_slow_notification_with.update(options)
    create_notification(**create_slow_notification_with)
    result = is_delivery_slow_for_providers(10, 5, 0.1)
    assert result["mmg"] == expected_result


def test_dao_get_notifications_by_recipient(sample_template):
    recipient_to_search_for = {"to_field": "+447700900855", "normalised_to": "447700900855"}

    notification1 = create_notification(template=sample_template, **recipient_to_search_for)
    create_notification(template=sample_template, key_type=KEY_TYPE_TEST, **recipient_to_search_for)
    create_notification(template=sample_template, to_field="jack@gmail.com", normalised_to="jack@gmail.com")
    create_notification(template=sample_template, to_field="jane@gmail.com", normalised_to="jane@gmail.com")

    results = dao_get_notifications_by_recipient_or_reference(
        notification1.service_id, recipient_to_search_for["to_field"], notification_type="sms"
    )

    assert len(results.items) == 1
    assert notification1.id == results.items[0].id


def test_dao_get_notifications_by_recipient_is_limited_to_50_results(sample_template):
    for _ in range(100):
        create_notification(
            template=sample_template,
            to_field="+447700900855",
            normalised_to="447700900855",
        )

    results = dao_get_notifications_by_recipient_or_reference(
        sample_template.service_id,
        "447700900855",
        notification_type="sms",
        page_size=50,
    )

    assert len(results.items) == 50


@pytest.mark.parametrize("search_term", ["JACK", "JACK@gmail.com", "jack@gmail.com"])
def test_dao_get_notifications_by_recipient_is_not_case_sensitive(sample_email_template, search_term):
    notification = create_notification(
        template=sample_email_template, to_field="jack@gmail.com", normalised_to="jack@gmail.com"
    )
    results = dao_get_notifications_by_recipient_or_reference(
        notification.service_id, search_term, notification_type="email"
    )
    notification_ids = [notification.id for notification in results.items]

    assert len(results.items) == 1
    assert notification.id in notification_ids


def test_dao_get_notifications_by_recipient_matches_partial_emails(sample_email_template):
    notification_1 = create_notification(
        template=sample_email_template, to_field="jack@gmail.com", normalised_to="jack@gmail.com"
    )
    notification_2 = create_notification(
        template=sample_email_template, to_field="jacque@gmail.com", normalised_to="jacque@gmail.com"
    )
    results = dao_get_notifications_by_recipient_or_reference(
        notification_1.service_id, "ack", notification_type="email"
    )
    notification_ids = [notification.id for notification in results.items]

    assert len(results.items) == 1
    assert notification_1.id in notification_ids
    assert notification_2.id not in notification_ids


@pytest.mark.parametrize(
    "search_term, expected_result_count",
    [
        ("foobar", 1),
        ("foo", 2),
        ("bar", 2),
        ("foo%", 1),
        ("%%bar", 1),
        ("%_", 1),
        ("%", 2),
        ("_", 1),
        ("/", 1),
        ("\\", 1),
        ("baz\\baz", 1),
        ("%foo", 0),
        ("%_%", 0),
        ("example.com", 5),
    ],
)
def test_dao_get_notifications_by_recipient_escapes(
    sample_email_template,
    search_term,
    expected_result_count,
):
    for email_address in {
        "foo%_@example.com",
        "%%bar@example.com",
        "foobar@example.com",
        "/@example.com",
        "baz\\baz@example.com",
    }:
        create_notification(
            template=sample_email_template,
            to_field=email_address,
            normalised_to=email_address,
        )

    assert (
        len(
            dao_get_notifications_by_recipient_or_reference(
                sample_email_template.service_id,
                search_term,
                notification_type="email",
            ).items
        )
        == expected_result_count
    )


@pytest.mark.parametrize(
    "search_term, expected_result_count",
    [
        ("foobar", 1),
        ("foo", 2),
        ("bar", 2),
        ("foo%", 1),
        ("%%bar", 1),
        ("%_", 1),
        ("%", 2),
        ("_", 1),
        ("/", 1),
        ("\\", 1),
        ("baz\\baz", 1),
        ("%foo", 0),
        ("%_%", 0),
        ("test@example.com", 5),
    ],
)
def test_dao_get_notifications_by_reference_escapes_special_character(
    sample_email_template,
    search_term,
    expected_result_count,
):
    for reference in {
        "foo%_",
        "%%bar",
        "foobar",
        "/",
        "baz\\baz",
    }:
        create_notification(
            template=sample_email_template,
            to_field="test@example.com",
            normalised_to="test@example.com",
            client_reference=reference,
        )

    assert (
        len(
            dao_get_notifications_by_recipient_or_reference(
                sample_email_template.service_id,
                search_term,
                notification_type="email",
            ).items
        )
        == expected_result_count
    )


@pytest.mark.parametrize(
    "search_term",
    [
        "001",
        "100",
        "09001",
        "077009001",
        "07700 9001",
        "(0)7700 9001",
        "4477009001",
        "+4477009001",
        pytest.param("+44077009001", marks=pytest.mark.skip(reason="No easy way to normalise this")),
        pytest.param("+44(0)77009001", marks=pytest.mark.skip(reason="No easy way to normalise this")),
    ],
)
def test_dao_get_notifications_by_recipient_matches_partial_phone_numbers(
    sample_template,
    search_term,
):
    notification_1 = create_notification(
        template=sample_template,
        to_field="+447700900100",
        normalised_to="447700900100",
    )
    notification_2 = create_notification(
        template=sample_template,
        to_field="+447700900200",
        normalised_to="447700900200",
    )
    results = dao_get_notifications_by_recipient_or_reference(
        notification_1.service_id, search_term, notification_type="sms"
    )
    notification_ids = [notification.id for notification in results.items]

    assert len(results.items) == 1
    assert notification_1.id in notification_ids
    assert notification_2.id not in notification_ids


@pytest.mark.parametrize("to", ["not@email", "123"])
def test_dao_get_notifications_by_recipient_accepts_invalid_phone_numbers_and_email_addresses(
    sample_template,
    to,
):
    notification = create_notification(
        template=sample_template, to_field="test@example.com", normalised_to="test@example.com"
    )
    results = dao_get_notifications_by_recipient_or_reference(notification.service_id, to, notification_type="email")
    assert len(results.items) == 0


def test_dao_get_notifications_by_recipient_ignores_spaces(sample_template):
    notification1 = create_notification(
        template=sample_template, to_field="+447700900855", normalised_to="447700900855"
    )
    notification2 = create_notification(
        template=sample_template, to_field="+44 77 00900 855", normalised_to="447700900855"
    )
    notification3 = create_notification(
        template=sample_template, to_field=" +4477009 00 855 ", normalised_to="447700900855"
    )
    create_notification(template=sample_template, to_field="jaCK@gmail.com", normalised_to="jack@gmail.com")

    results = dao_get_notifications_by_recipient_or_reference(
        notification1.service_id, "+447700900855", notification_type="sms"
    )
    notification_ids = [notification.id for notification in results.items]

    assert len(results.items) == 3
    assert notification1.id in notification_ids
    assert notification2.id in notification_ids
    assert notification3.id in notification_ids


@pytest.mark.parametrize("phone_search", ("077", "7-7", "+44(0)7711 111111"))
@pytest.mark.parametrize(
    "email_search",
    (
        "example",
        "eXaMpLe",
    ),
)
def test_dao_get_notifications_by_recipient_searches_across_notification_types(
    notify_db_session,
    phone_search,
    email_search,
):
    service = create_service()
    sms_template = create_template(service=service)
    email_template = create_template(service=service, template_type="email")
    sms = create_notification(template=sms_template, to_field="07711111111", normalised_to="447711111111")
    email = create_notification(template=email_template, to_field="077@example.com", normalised_to="077@example.com")

    results = dao_get_notifications_by_recipient_or_reference(service.id, phone_search, notification_type="sms")
    assert len(results.items) == 1
    assert results.items[0].id == sms.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, email_search, notification_type="email")
    assert len(results.items) == 1
    assert results.items[0].id == email.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "77")
    assert len(results.items) == 2
    assert results.items[0].id == email.id
    assert results.items[1].id == sms.id


def test_dao_get_notifications_by_reference(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service)
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")
    sms = create_notification(
        template=sms_template,
        to_field="07711111111",
        normalised_to="447711111111",
        client_reference="77aA",
    )
    email = create_notification(
        template=email_template,
        to_field="077@example.com",
        normalised_to="077@example.com",
        client_reference="77bB",
    )
    letter = create_notification(
        template=letter_template,
        to_field="123 Example Street\nXX1X 1XX",
        normalised_to="123examplestreetxx1x1xx",
        client_reference="77bB",
    )

    results = dao_get_notifications_by_recipient_or_reference(service.id, "77")
    assert len(results.items) == 3
    assert results.items[0].id == letter.id
    assert results.items[1].id == email.id
    assert results.items[2].id == sms.id

    # If notification_type isn’t specified then we can’t normalise the
    # phone number to 4477… so this query will only find the email sent
    # to 077@example.com
    results = dao_get_notifications_by_recipient_or_reference(service.id, "077")
    assert len(results.items) == 1
    assert results.items[0].id == email.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "077@")
    assert len(results.items) == 1
    assert results.items[0].id == email.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "077", notification_type="sms")
    assert len(results.items) == 1
    assert results.items[0].id == sms.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "77", notification_type="sms")
    assert len(results.items) == 1
    assert results.items[0].id == sms.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "Aa", notification_type="sms")
    assert len(results.items) == 1
    assert results.items[0].id == sms.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "bB", notification_type="sms")
    assert len(results.items) == 0

    results = dao_get_notifications_by_recipient_or_reference(service.id, "77", notification_type="email")
    assert len(results.items) == 1
    assert results.items[0].id == email.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "Bb", notification_type="email")
    assert len(results.items) == 1
    assert results.items[0].id == email.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "aA", notification_type="email")
    assert len(results.items) == 0

    results = dao_get_notifications_by_recipient_or_reference(service.id, "aA", notification_type="letter")
    assert len(results.items) == 0

    results = dao_get_notifications_by_recipient_or_reference(service.id, "123")
    assert len(results.items) == 1
    assert results.items[0].id == letter.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "xX 1x1  Xx")
    assert len(results.items) == 1
    assert results.items[0].id == letter.id

    results = dao_get_notifications_by_recipient_or_reference(service.id, "77", notification_type="letter")
    assert len(results.items) == 1
    assert results.items[0].id == letter.id


def test_dao_get_notifications_by_to_field_filters_status(sample_template):
    notification = create_notification(
        template=sample_template, to_field="+447700900855", normalised_to="447700900855", status="delivered"
    )
    create_notification(
        template=sample_template, to_field="+447700900855", normalised_to="447700900855", status="temporary-failure"
    )

    notifications = dao_get_notifications_by_recipient_or_reference(
        notification.service_id,
        "+447700900855",
        statuses=["delivered"],
        notification_type="sms",
    )

    assert len(notifications.items) == 1
    assert notification.id == notifications.items[0].id


def test_dao_get_notifications_by_to_field_filters_multiple_statuses(sample_template):
    notification1 = create_notification(
        template=sample_template, to_field="+447700900855", normalised_to="447700900855", status="delivered"
    )
    notification2 = create_notification(
        template=sample_template, to_field="+447700900855", normalised_to="447700900855", status="sending"
    )

    notifications = dao_get_notifications_by_recipient_or_reference(
        notification1.service_id, "+447700900855", statuses=["delivered", "sending"], notification_type="sms"
    )
    notification_ids = [notification.id for notification in notifications.items]

    assert len(notifications.items) == 2
    assert notification1.id in notification_ids
    assert notification2.id in notification_ids


def test_dao_get_notifications_by_to_field_returns_all_if_no_status_filter(sample_template):
    notification1 = create_notification(
        template=sample_template, to_field="+447700900855", normalised_to="447700900855", status="delivered"
    )
    notification2 = create_notification(
        template=sample_template, to_field="+447700900855", normalised_to="447700900855", status="temporary-failure"
    )

    notifications = dao_get_notifications_by_recipient_or_reference(
        notification1.service_id, "+447700900855", notification_type="sms"
    )
    notification_ids = [notification.id for notification in notifications.items]

    assert len(notifications.items) == 2
    assert notification1.id in notification_ids
    assert notification2.id in notification_ids


@freeze_time("2016-01-01 11:10:00")
def test_dao_get_notifications_by_to_field_orders_by_created_at_desc(sample_template):
    notification = partial(
        create_notification, template=sample_template, to_field="+447700900855", normalised_to="447700900855"
    )

    notification_a_minute_ago = notification(created_at=datetime.utcnow() - timedelta(minutes=1))
    notification = notification(created_at=datetime.utcnow())

    notifications = dao_get_notifications_by_recipient_or_reference(
        sample_template.service_id, "+447700900855", notification_type="sms"
    )

    assert len(notifications.items) == 2
    assert notifications.items[0].id == notification.id
    assert notifications.items[1].id == notification_a_minute_ago.id


def test_dao_get_last_notification_added_for_job_id_valid_job_id(sample_template):
    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)
    last = create_notification(sample_template, job, 2)

    assert dao_get_last_notification_added_for_job_id(job.id) == last


def test_dao_get_last_notification_added_for_job_id_no_notifications(sample_template):
    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )

    assert dao_get_last_notification_added_for_job_id(job.id) is None


def test_dao_get_last_notification_added_for_job_id_no_job(sample_template, fake_uuid):
    assert dao_get_last_notification_added_for_job_id(fake_uuid) is None


def test_dao_update_notifications_by_reference_updated_notifications(sample_template):
    notification_1 = create_notification(template=sample_template, reference="ref1")
    notification_2 = create_notification(template=sample_template, reference="ref2")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref1", "ref2"], update_dict={"status": "delivered", "billable_units": 2}
    )
    assert updated_count == 2
    updated_1 = Notification.query.get(notification_1.id)
    assert updated_1.billable_units == 2
    assert updated_1.status == "delivered"
    updated_2 = Notification.query.get(notification_2.id)
    assert updated_2.billable_units == 2
    assert updated_2.status == "delivered"

    assert updated_history_count == 0


def test_dao_update_notifications_by_reference_updates_history_some_notifications_exist(sample_template):
    create_notification(template=sample_template, reference="ref1")
    create_notification_history(template=sample_template, reference="ref2")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref1", "ref2"], update_dict={"status": "delivered", "billable_units": 2}
    )
    assert updated_count == 1
    assert updated_history_count == 1


def test_dao_update_notifications_by_reference_updates_history_no_notifications_exist(sample_template):
    create_notification_history(template=sample_template, reference="ref1")
    create_notification_history(template=sample_template, reference="ref2")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref1", "ref2"], update_dict={"status": "delivered", "billable_units": 2}
    )
    assert updated_count == 0
    assert updated_history_count == 2


def test_dao_update_notifications_by_reference_returns_zero_when_no_notifications_to_update(notify_db_session):
    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref"], update_dict={"status": "delivered", "billable_units": 2}
    )

    assert updated_count == 0
    assert updated_history_count == 0


def test_dao_update_notifications_by_reference_set_returned_letter_status(sample_letter_template):
    notification = create_notification(template=sample_letter_template, reference="ref")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref"], update_dict={"status": "returned-letter"}
    )

    assert updated_count == 1
    assert updated_history_count == 0
    updated_notification = Notification.query.get(notification.id)
    assert updated_notification.status == "returned-letter"
    assert updated_notification.updated_at <= datetime.utcnow()


def test_dao_update_notifications_by_reference_updates_history_when_one_of_two_notifications_exists(
    sample_letter_template,
):
    notification1 = create_notification_history(template=sample_letter_template, reference="ref1")
    notification2 = create_notification(template=sample_letter_template, reference="ref2")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref1", "ref2"], update_dict={"status": "returned-letter"}
    )

    assert updated_count == 1
    assert updated_history_count == 1
    assert Notification.query.get(notification2.id).status == "returned-letter"
    assert NotificationHistory.query.get(notification1.id).status == "returned-letter"


def test_dao_get_notification_by_reference_with_one_match_returns_notification(sample_letter_template):
    create_notification(template=sample_letter_template, reference="REF1")
    notification = dao_get_notification_by_reference("REF1")

    assert notification.reference == "REF1"


def test_dao_get_notification_by_reference_with_multiple_matches_raises_error(sample_letter_template):
    create_notification(template=sample_letter_template, reference="REF1")
    create_notification(template=sample_letter_template, reference="REF1")

    with pytest.raises(SQLAlchemyError):
        dao_get_notification_by_reference("REF1")


def test_dao_get_notification_by_reference_with_no_matches_raises_error(notify_db_session):
    with pytest.raises(SQLAlchemyError):
        dao_get_notification_by_reference("REF1")


def test_dao_get_notification_or_history_by_reference_with_one_match_returns_notification(sample_letter_template):
    create_notification(template=sample_letter_template, reference="REF1")
    notification = dao_get_notification_or_history_by_reference("REF1")

    assert notification.reference == "REF1"


def test_dao_get_notification_or_history_by_reference_with_multiple_matches_raises_error(sample_letter_template):
    create_notification(template=sample_letter_template, reference="REF1")
    create_notification(template=sample_letter_template, reference="REF1")

    with pytest.raises(SQLAlchemyError):
        dao_get_notification_or_history_by_reference("REF1")


def test_dao_get_notification_or_history_by_reference_with_no_matches_raises_error(notify_db_session):
    with pytest.raises(SQLAlchemyError):
        dao_get_notification_or_history_by_reference("REF1")


@pytest.mark.parametrize("notification_type", ["letter", "email", "sms"])
def test_notifications_not_yet_sent(sample_service, notification_type):
    older_than = 4  # number of seconds the notification can not be older than
    template = create_template(service=sample_service, template_type=notification_type)
    old_notification = create_notification(
        template=template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="created"
    )
    create_notification(
        template=template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="sending"
    )
    create_notification(template=template, created_at=datetime.utcnow(), status="created")

    results = notifications_not_yet_sent(older_than, notification_type)
    assert len(results) == 1
    assert results[0] == old_notification


@pytest.mark.parametrize("notification_type", ["letter", "email", "sms"])
def test_notifications_not_yet_sent_return_no_rows(sample_service, notification_type):
    older_than = 5  # number of seconds the notification can not be older than
    template = create_template(service=sample_service, template_type=notification_type)
    create_notification(template=template, created_at=datetime.utcnow(), status="created")
    create_notification(template=template, created_at=datetime.utcnow(), status="sending")
    create_notification(template=template, created_at=datetime.utcnow(), status="delivered")

    results = notifications_not_yet_sent(older_than, notification_type)
    assert len(results) == 0


def test_letters_to_be_printed_sort_by_service(notify_db_session):
    first_service = create_service(service_name="first service", service_id="3a5cea08-29fd-4bb9-b582-8dedd928b149")
    second_service = create_service(service_name="second service", service_id="642bf33b-54b5-45f2-8c13-942a46616704")
    first_template = create_template(service=first_service, template_type="letter", postage="second")
    second_template = create_template(service=second_service, template_type="letter", postage="second")
    letters_ordered_by_service_then_time = [
        create_notification(template=first_template, created_at=datetime(2020, 12, 1, 9, 30)),
        create_notification(template=first_template, created_at=datetime(2020, 12, 1, 12, 30)),
        create_notification(template=first_template, created_at=datetime(2020, 12, 1, 13, 30)),
        create_notification(template=first_template, created_at=datetime(2020, 12, 1, 14, 30)),
        create_notification(template=first_template, created_at=datetime(2020, 12, 1, 15, 30)),
        create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 30)),
        create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 31)),
        create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 32)),
        create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 33)),
        create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 34)),
    ]

    results = list(
        dao_get_letters_to_be_printed(
            print_run_deadline_local=datetime(2020, 12, 1, 17, 30), postage="second", query_limit=4
        )
    )
    assert [x.id for x in results] == [x.id for x in letters_ordered_by_service_then_time]


def test_letters_to_be_printed_does_not_include_letters_without_billable_units_set(
    notify_db_session, sample_letter_template
):
    included_letter = create_notification(
        template=sample_letter_template, created_at=datetime(2020, 12, 1, 9, 30), billable_units=3
    )
    create_notification(template=sample_letter_template, created_at=datetime(2020, 12, 1, 9, 31), billable_units=0)

    results = list(
        dao_get_letters_to_be_printed(
            print_run_deadline_local=datetime(2020, 12, 1, 17, 30), postage="second", query_limit=4
        )
    )
    assert len(results) == 1
    assert results[0].id == included_letter.id


def test_dao_get_letters_and_sheets_volume_by_postage(notify_db_session):
    first_service = create_service(service_name="first service", service_id="3a5cea08-29fd-4bb9-b582-8dedd928b149")
    second_service = create_service(service_name="second service", service_id="642bf33b-54b5-45f2-8c13-942a46616704")
    first_template = create_template(service=first_service, template_type="letter", postage="second")
    second_template = create_template(service=second_service, template_type="letter", postage="second")
    create_notification(template=first_template, created_at=datetime(2020, 12, 1, 9, 30), postage="first")
    create_notification(template=first_template, created_at=datetime(2020, 12, 1, 12, 30), postage="europe")
    create_notification(template=first_template, created_at=datetime(2020, 12, 1, 13, 30), postage="rest-of-world")
    create_notification(template=first_template, created_at=datetime(2020, 12, 1, 14, 30), billable_units=3)
    create_notification(template=first_template, created_at=datetime(2020, 12, 1, 14, 30), billable_units=0)
    create_notification(template=first_template, created_at=datetime(2020, 12, 1, 15, 30))
    create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 30), postage="first")
    create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 31), postage="first")
    create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 32))
    create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 33))
    create_notification(template=second_template, created_at=datetime(2020, 12, 1, 8, 34))

    results = dao_get_letters_and_sheets_volume_by_postage(print_run_deadline_local=datetime(2020, 12, 1, 17, 30))

    assert len(results) == 4

    expected_results = [
        {"letters_count": 1, "sheets_count": 1, "postage": "europe"},
        {"letters_count": 3, "sheets_count": 3, "postage": "first"},
        {"letters_count": 1, "sheets_count": 1, "postage": "rest-of-world"},
        {"letters_count": 5, "sheets_count": 7, "postage": "second"},
    ]

    for result in results:
        assert result._asdict() in expected_results


@pytest.mark.parametrize(
    "created_at_utc,date_to_check,expected_count",
    [
        # Clocks change on the 27th of March 2022, so the query needs to look at the
        # time range 00:00 - 23:00 (UTC) thereafter.
        ("2022-03-27T00:30", date(2022, 3, 27), 1),  # 27/03 00:30 GMT
        ("2022-03-27T22:30", date(2022, 3, 27), 1),  # 27/03 23:30 BST
        ("2022-03-27T23:30", date(2022, 3, 27), 0),  # 28/03 00:30 BST
        ("2022-03-26T23:30", date(2022, 3, 26), 1),  # 26/03 23:30 GMT
    ],
)
def test_get_service_ids_with_notifications_on_date_respects_gmt_bst(
    sample_template, created_at_utc, date_to_check, expected_count
):
    create_notification(template=sample_template, created_at=created_at_utc)
    service_ids = get_service_ids_with_notifications_on_date(SMS_TYPE, date_to_check)
    assert len(service_ids) == expected_count


def test_get_service_ids_with_notifications_on_date_checks_ft_status(
    sample_template,
):
    create_notification(template=sample_template, created_at="2022-01-01T09:30")
    create_ft_notification_status(template=sample_template, bst_date="2022-01-02")

    assert len(get_service_ids_with_notifications_on_date(SMS_TYPE, date(2022, 1, 1))) == 1
    assert len(get_service_ids_with_notifications_on_date(SMS_TYPE, date(2022, 1, 2))) == 1


def test_dao_get_notification_or_history_by_id_when_notification_exists(sample_notification):
    notification = dao_get_notification_or_history_by_id(sample_notification.id)

    assert sample_notification == notification


def test_dao_get_notification_or_history_by_id_when_notification_history_exists(sample_notification_history):
    notification = dao_get_notification_or_history_by_id(sample_notification_history.id)

    assert sample_notification_history == notification


def test_dao_record_letter_despatched_on_by_id(notify_db_session):
    notification_id = uuid.uuid4()

    dao_record_letter_despatched_on_by_id(notification_id, date(2024, 3, 7), LetterCostThreshold("sorted"))
    letter_despatch = NotificationLetterDespatch.query.one()

    assert letter_despatch.notification_id == notification_id
    assert letter_despatch.despatched_on == date(2024, 3, 7)
    assert letter_despatch.cost_threshold == LetterCostThreshold.sorted

    # Calling the function with a notification_id that already exists updates the row
    dao_record_letter_despatched_on_by_id(notification_id, date(2024, 3, 8), LetterCostThreshold("unsorted"))
    letter_despatch = NotificationLetterDespatch.query.one()

    assert letter_despatch.notification_id == notification_id
    assert letter_despatch.despatched_on == date(2024, 3, 8)
    assert letter_despatch.cost_threshold == LetterCostThreshold.unsorted
