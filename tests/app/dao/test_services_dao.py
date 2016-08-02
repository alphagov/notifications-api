from datetime import datetime
import uuid
import functools

import pytest
from sqlalchemy.orm.exc import FlushError, NoResultFound
from sqlalchemy.exc import IntegrityError
from freezegun import freeze_time

from app import db
from app.dao.services_dao import (
    dao_create_service,
    dao_add_user_to_service,
    dao_remove_user_from_service,
    dao_fetch_all_services,
    dao_fetch_service_by_id,
    dao_fetch_all_services_by_user,
    dao_update_service,
    delete_service_and_all_associated_db_objects,
    dao_fetch_stats_for_service,
    dao_fetch_todays_stats_for_service,
    dao_fetch_weekly_historical_stats_for_service
)
from app.dao.users_dao import save_model_user
from app.models import (
    NotificationStatistics,
    TemplateStatistics,
    ProviderStatistics,
    VerifyCode,
    ApiKey,
    Template,
    Job,
    Notification,
    NotificationHistory,
    Permission,
    User,
    InvitedUser,
    Service
)

from tests.app.conftest import (
    sample_notification as create_notification,
    sample_notification_history as create_notification_history
)


def test_create_service(sample_user):
    assert Service.query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      active=True,
                      restricted=False,
                      created_by=sample_user)
    dao_create_service(service, sample_user)
    assert Service.query.count() == 1
    assert Service.query.first().name == "service_name"
    assert Service.query.first().id == service.id
    assert not Service.query.first().research_mode
    assert sample_user in Service.query.first().users


def test_cannot_create_two_services_with_same_name(sample_user):
    assert Service.query.count() == 0
    service1 = Service(name="service_name",
                       email_from="email_from1",
                       message_limit=1000,
                       active=True,
                       restricted=False,
                       created_by=sample_user)

    service2 = Service(name="service_name",
                       email_from="email_from2",
                       message_limit=1000,
                       active=True,
                       restricted=False,
                       created_by=sample_user)
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, sample_user)
        dao_create_service(service2, sample_user)
    assert 'duplicate key value violates unique constraint "services_name_key"' in str(excinfo.value)


def test_cannot_create_two_services_with_same_email_from(sample_user):
    assert Service.query.count() == 0
    service1 = Service(name="service_name1",
                       email_from="email_from",
                       message_limit=1000,
                       active=True,
                       restricted=False,
                       created_by=sample_user)
    service2 = Service(name="service_name2",
                       email_from="email_from",
                       message_limit=1000,
                       active=True,
                       restricted=False,
                       created_by=sample_user)
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, sample_user)
        dao_create_service(service2, sample_user)
    assert 'duplicate key value violates unique constraint "services_email_from_key"' in str(excinfo.value)


def test_cannot_create_service_with_no_user(notify_db_session, sample_user):
    assert Service.query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      active=True,
                      restricted=False,
                      created_by=sample_user)
    with pytest.raises(FlushError) as excinfo:
        dao_create_service(service, None)
    assert "Can't flush None value found in collection Service.users" in str(excinfo.value)


def test_should_add_user_to_service(sample_user):
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      active=True,
                      restricted=False,
                      created_by=sample_user)
    dao_create_service(service, sample_user)
    assert sample_user in Service.query.first().users
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users


def test_should_remove_user_from_service(sample_user):
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      active=True,
                      restricted=False,
                      created_by=sample_user)
    dao_create_service(service, sample_user)
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users
    dao_remove_user_from_service(service, new_user)
    assert new_user not in Service.query.first().users


def test_get_all_services(service_factory):
    service_factory.get('service 1', email_from='service.1')
    assert len(dao_fetch_all_services()) == 1
    assert dao_fetch_all_services()[0].name == 'service 1'

    service_factory.get('service 2', email_from='service.2')
    assert len(dao_fetch_all_services()) == 2
    assert dao_fetch_all_services()[1].name == 'service 2'


def test_get_all_services_should_return_in_created_order(service_factory):
    service_factory.get('service 1', email_from='service.1')
    service_factory.get('service 2', email_from='service.2')
    service_factory.get('service 3', email_from='service.3')
    service_factory.get('service 4', email_from='service.4')
    assert len(dao_fetch_all_services()) == 4
    assert dao_fetch_all_services()[0].name == 'service 1'
    assert dao_fetch_all_services()[1].name == 'service 2'
    assert dao_fetch_all_services()[2].name == 'service 3'
    assert dao_fetch_all_services()[3].name == 'service 4'


def test_get_all_services_should_return_empty_list_if_no_services():
    assert len(dao_fetch_all_services()) == 0


def test_get_all_services_for_user(service_factory, sample_user):
    service_factory.get('service 1', sample_user, email_from='service.1')
    service_factory.get('service 2', sample_user, email_from='service.2')
    service_factory.get('service 3', sample_user, email_from='service.3')
    assert len(dao_fetch_all_services_by_user(sample_user.id)) == 3
    assert dao_fetch_all_services_by_user(sample_user.id)[0].name == 'service 1'
    assert dao_fetch_all_services_by_user(sample_user.id)[1].name == 'service 2'
    assert dao_fetch_all_services_by_user(sample_user.id)[2].name == 'service 3'


def test_get_all_only_services_user_has_access_to(service_factory, sample_user):
    service_factory.get('service 1', sample_user, email_from='service.1')
    service_factory.get('service 2', sample_user, email_from='service.2')
    service_3 = service_factory.get('service 3', sample_user, email_from='service.3')
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    dao_add_user_to_service(service_3, new_user)
    assert len(dao_fetch_all_services_by_user(sample_user.id)) == 3
    assert dao_fetch_all_services_by_user(sample_user.id)[0].name == 'service 1'
    assert dao_fetch_all_services_by_user(sample_user.id)[1].name == 'service 2'
    assert dao_fetch_all_services_by_user(sample_user.id)[2].name == 'service 3'
    assert len(dao_fetch_all_services_by_user(new_user.id)) == 1
    assert dao_fetch_all_services_by_user(new_user.id)[0].name == 'service 3'


def test_get_all_user_services_should_return_empty_list_if_no_services_for_user(sample_user):
    assert len(dao_fetch_all_services_by_user(sample_user.id)) == 0


def test_get_service_by_id_returns_none_if_no_service(notify_db):
    with pytest.raises(NoResultFound) as e:
        dao_fetch_service_by_id(str(uuid.uuid4()))
    assert 'No row was found for one()' in str(e)


def test_get_service_by_id_returns_service(service_factory):
    service = service_factory.get('testing', email_from='testing')
    assert dao_fetch_service_by_id(service.id).name == 'testing'


def test_create_service_creates_a_history_record_with_current_data(sample_user):
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      active=True,
                      restricted=False,
                      created_by=sample_user)
    dao_create_service(service, sample_user)
    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 1

    service_from_db = Service.query.first()
    service_history = Service.get_history_model().query.first()

    assert service_from_db.id == service_history.id
    assert service_from_db.name == service_history.name
    assert service_from_db.version == 1
    assert service_from_db.version == service_history.version
    assert sample_user.id == service_history.created_by_id
    assert service_from_db.created_by.id == service_history.created_by_id


def test_update_service_creates_a_history_record_with_current_data(sample_user):
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      active=True,
                      restricted=False,
                      created_by=sample_user)
    dao_create_service(service, sample_user)

    assert Service.query.count() == 1
    assert Service.query.first().version == 1
    assert Service.get_history_model().query.count() == 1

    service.name = 'updated_service_name'
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 2

    service_from_db = Service.query.first()

    assert service_from_db.version == 2

    assert Service.get_history_model().query.filter_by(name='service_name').one().version == 1
    assert Service.get_history_model().query.filter_by(name='updated_service_name').one().version == 2


def test_create_service_and_history_is_transactional(sample_user):
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name=None,
                      email_from="email_from",
                      message_limit=1000,
                      active=True,
                      restricted=False,
                      created_by=sample_user)

    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service, sample_user)

    assert 'column "name" violates not-null constraint' in str(excinfo.value)
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0


def test_delete_service_and_associated_objects(notify_db,
                                               notify_db_session,
                                               sample_user,
                                               sample_service,
                                               sample_email_code,
                                               sample_sms_code,
                                               sample_template,
                                               sample_email_template,
                                               sample_api_key,
                                               sample_job,
                                               sample_notification,
                                               sample_invited_user,
                                               sample_permission,
                                               sample_provider_statistics):
    delete_service_and_all_associated_db_objects(sample_service)
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0
    assert ProviderStatistics.query.count() == 0
    assert VerifyCode.query.count() == 0
    assert ApiKey.query.count() == 0
    assert ApiKey.get_history_model().query.count() == 0
    assert Template.query.count() == 0
    assert Template.get_history_model().query.count() == 0
    assert Job.query.count() == 0
    assert Notification.query.count() == 0
    assert Permission.query.count() == 0
    assert User.query.count() == 0
    assert InvitedUser.query.count() == 0
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0


def test_add_existing_user_to_another_service_doesnot_change_old_permissions(sample_user):

    service_one = Service(name="service_one",
                          email_from="service_one",
                          message_limit=1000,
                          active=True,
                          restricted=False,
                          created_by=sample_user)

    dao_create_service(service_one, sample_user)
    assert sample_user.id == service_one.users[0].id
    test_user_permissions = Permission.query.filter_by(service=service_one, user=sample_user).all()
    assert len(test_user_permissions) == 8

    other_user = User(
        name='Other Test User',
        email_address='other_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900987'
    )
    save_model_user(other_user)
    service_two = Service(name="service_two",
                          email_from="service_two",
                          message_limit=1000,
                          active=True,
                          restricted=False,
                          created_by=other_user)
    dao_create_service(service_two, other_user)

    assert other_user.id == service_two.users[0].id
    other_user_permissions = Permission.query.filter_by(service=service_two, user=other_user).all()
    assert len(other_user_permissions) == 8

    other_user_service_one_permissions = Permission.query.filter_by(service=service_one, user=other_user).all()
    assert len(other_user_service_one_permissions) == 0

    # adding the other_user to service_one should leave all other_user permissions on service_two intact
    permissions = []
    for p in ['send_emails', 'send_texts', 'send_letters']:
        permissions.append(Permission(permission=p))

    dao_add_user_to_service(service_one, other_user, permissions=permissions)

    other_user_service_one_permissions = Permission.query.filter_by(service=service_one, user=other_user).all()
    assert len(other_user_service_one_permissions) == 3

    other_user_service_two_permissions = Permission.query.filter_by(service=service_two, user=other_user).all()
    assert len(other_user_service_two_permissions) == 8


def test_fetch_stats_filters_on_service(sample_notification):
    service_two = Service(name="service_two",
                          created_by=sample_notification.service.created_by,
                          email_from="hello",
                          active=False,
                          restricted=False,
                          message_limit=1000)
    dao_create_service(service_two, sample_notification.service.created_by)

    stats = dao_fetch_stats_for_service(service_two.id)
    assert len(stats) == 0


def test_fetch_stats_ignores_historical_notification_data(sample_notification):
    service_id = sample_notification.service.id

    db.session.delete(sample_notification)

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 1

    stats = dao_fetch_stats_for_service(service_id)
    assert len(stats) == 0


def test_fetch_stats_counts_correctly(notify_db, notify_db_session, sample_template, sample_email_template):
    # two created email, one failed email, and one created sms
    create_notification(notify_db, notify_db_session, template=sample_email_template, status='created')
    create_notification(notify_db, notify_db_session, template=sample_email_template, status='created')
    create_notification(notify_db, notify_db_session, template=sample_email_template, status='technical-failure')
    create_notification(notify_db, notify_db_session, template=sample_template, status='created')

    stats = dao_fetch_stats_for_service(sample_template.service_id)
    stats = sorted(stats, key=lambda x: (x.notification_type, x.status))
    assert len(stats) == 3

    assert stats[0].notification_type == 'email'
    assert stats[0].status == 'created'
    assert stats[0].count == 2

    assert stats[1].notification_type == 'email'
    assert stats[1].status == 'technical-failure'
    assert stats[1].count == 1

    assert stats[2].notification_type == 'sms'
    assert stats[2].status == 'created'
    assert stats[2].count == 1


def test_fetch_stats_for_today_only_includes_today(notify_db, notify_db_session, sample_template):
    # two created email, one failed email, and one created sms
    with freeze_time('2001-01-01T23:59:00'):
        just_before_midnight_yesterday = create_notification(notify_db, None, to_field='1', status='delivered')

    with freeze_time('2001-01-02T00:01:00'):
        just_after_midnight_today = create_notification(notify_db, None, to_field='2', status='failed')

    with freeze_time('2001-01-02T12:00:00'):
        right_now = create_notification(notify_db, None, to_field='3', status='created')

        stats = dao_fetch_todays_stats_for_service(sample_template.service_id)

    stats = {row.status: row.count for row in stats}
    assert 'delivered' not in stats
    assert stats['failed'] == 1
    assert stats['created'] == 1


def test_fetch_weekly_historical_stats_separates_weeks(notify_db, notify_db_session, sample_template):
    notification_history = functools.partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        sample_template
    )
    week_53_last_yr = notification_history(created_at=datetime(2016, 1, 1))
    week_1_last_yr = notification_history(created_at=datetime(2016, 1, 5))
    last_sunday = notification_history(created_at=datetime(2016, 7, 24, 23, 59))
    last_monday_morning = notification_history(created_at=datetime(2016, 7, 25, 0, 0))
    last_monday_evening = notification_history(created_at=datetime(2016, 7, 25, 23, 59))

    with freeze_time('Wed 27th July 2016'):
        today = notification_history(created_at=datetime.now(), status='delivered')
        ret = dao_fetch_weekly_historical_stats_for_service(sample_template.service_id)

    assert [(row.week_start, row.status) for row in ret] == [
        (datetime(2015, 12, 28), 'created'),
        (datetime(2016, 1, 4), 'created'),
        (datetime(2016, 7, 18), 'created'),
        (datetime(2016, 7, 25), 'created'),
        (datetime(2016, 7, 25), 'delivered')
    ]
    assert ret[-2].count == 2
    assert ret[-1].count == 1


def test_fetch_weekly_historical_stats_ignores_second_service(notify_db, notify_db_session, service_factory):
    template_1 = service_factory.get('1').templates[0]
    template_2 = service_factory.get('2').templates[0]

    notification_history = functools.partial(
        create_notification_history,
        notify_db,
        notify_db_session
    )
    last_sunday = notification_history(template_1, created_at=datetime(2016, 7, 24, 23, 59))
    last_monday_morning = notification_history(template_2, created_at=datetime(2016, 7, 25, 0, 0))

    with freeze_time('Wed 27th July 2016'):
        ret = dao_fetch_weekly_historical_stats_for_service(template_1.service_id)

    assert len(ret) == 1
    assert ret[0].week_start == datetime(2016, 7, 18)
    assert ret[0].count == 1


def test_fetch_weekly_historical_stats_separates_types(notify_db,
                                                       notify_db_session,
                                                       sample_template,
                                                       sample_email_template):
    notification_history = functools.partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        created_at=datetime(2016, 7, 25)
    )

    notification_history(sample_template)
    notification_history(sample_email_template)

    with freeze_time('Wed 27th July 2016'):
        ret = dao_fetch_weekly_historical_stats_for_service(sample_template.service_id)

    assert len(ret) == 2
    assert ret[0].week_start == datetime(2016, 7, 25)
    assert ret[0].count == 1
    assert ret[0].notification_type == 'email'
    assert ret[1].week_start == datetime(2016, 7, 25)
    assert ret[1].count == 1
    assert ret[1].notification_type == 'sms'
