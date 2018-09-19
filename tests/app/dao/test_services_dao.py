import uuid
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import FlushError, NoResultFound

from app import db
from app.celery.scheduled_tasks import daily_stats_template_usage_by_month
from app.dao.inbound_numbers_dao import (
    dao_set_inbound_number_to_service,
    dao_get_available_inbound_numbers,
    dao_set_inbound_number_active_flag
)
from app.dao.service_permissions_dao import dao_add_service_permission, dao_remove_service_permission
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
    fetch_todays_total_message_count,
    dao_fetch_todays_stats_for_all_services,
    fetch_stats_by_date_range_for_all_services,
    dao_suspend_service,
    dao_resume_service,
    dao_fetch_active_users_for_service,
    dao_fetch_service_by_inbound_number,
    dao_fetch_monthly_historical_stats_by_template,
    dao_fetch_monthly_historical_usage_by_template_for_service
)
from app.dao.users_dao import save_model_user, create_user_code
from app.models import (
    VerifyCode,
    ApiKey,
    Template,
    TemplateHistory,
    Job,
    Notification,
    NotificationHistory,
    Permission,
    User,
    InvitedUser,
    Service,
    ServicePermission,
    ServicePermissionTypes,
    DVLA_ORG_HM_GOVERNMENT,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    EMAIL_TYPE,
    SMS_TYPE,
    INTERNATIONAL_SMS_TYPE,
    LETTER_TYPE,
    SERVICE_PERMISSION_TYPES
)
from tests.app.db import (
    create_inbound_number,
    create_user,
    create_service,
    create_service_with_inbound_number,
    create_service_with_defined_sms_sender,
    create_template,
    create_notification,
    create_api_key,
    create_invited_user
)


def test_should_have_decorated_services_dao_functions():
    assert dao_fetch_todays_stats_for_service.__wrapped__.__name__ == 'dao_fetch_todays_stats_for_service'  # noqa
    assert dao_fetch_stats_for_service.__wrapped__.__name__ == 'dao_fetch_stats_for_service'  # noqa


def test_create_service(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      organisation_type='central',
                      created_by=user)
    dao_create_service(service, user)
    assert Service.query.count() == 1
    service_db = Service.query.one()
    assert service_db.name == "service_name"
    assert service_db.id == service.id
    assert service_db.dvla_organisation_id == DVLA_ORG_HM_GOVERNMENT
    assert service_db.email_from == 'email_from'
    assert service_db.research_mode is False
    assert service_db.prefix_sms is True
    assert service_db.postage == 'second'
    assert service.active is True
    assert user in service_db.users
    assert service_db.organisation_type == 'central'
    assert service_db.crown is True


def test_cannot_create_two_services_with_same_name(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service1 = Service(name="service_name",
                       email_from="email_from1",
                       message_limit=1000,
                       restricted=False,
                       created_by=user, )

    service2 = Service(name="service_name",
                       email_from="email_from2",
                       message_limit=1000,
                       restricted=False,
                       created_by=user)
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, user)
        dao_create_service(service2, user)
    assert 'duplicate key value violates unique constraint "services_name_key"' in str(excinfo.value)


def test_cannot_create_two_services_with_same_email_from(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service1 = Service(name="service_name1",
                       email_from="email_from",
                       message_limit=1000,
                       restricted=False,
                       created_by=user)
    service2 = Service(name="service_name2",
                       email_from="email_from",
                       message_limit=1000,
                       restricted=False,
                       created_by=user)
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, user)
        dao_create_service(service2, user)
    assert 'duplicate key value violates unique constraint "services_email_from_key"' in str(excinfo.value)


def test_cannot_create_service_with_no_user(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      created_by=user)
    with pytest.raises(FlushError) as excinfo:
        dao_create_service(service, None)
    assert "Can't flush None value found in collection Service.users" in str(excinfo.value)


def test_should_add_user_to_service(notify_db_session):
    user = create_user()
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      created_by=user)
    dao_create_service(service, user)
    assert user in Service.query.first().users
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users


def test_should_remove_user_from_service(notify_db_session):
    user = create_user()
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      created_by=user)
    dao_create_service(service, user)
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


def test_get_all_services(notify_db_session):
    create_service(service_name='service 1', email_from='service.1')
    assert len(dao_fetch_all_services()) == 1
    assert dao_fetch_all_services()[0].name == 'service 1'

    create_service(service_name='service 2', email_from='service.2')
    assert len(dao_fetch_all_services()) == 2
    assert dao_fetch_all_services()[1].name == 'service 2'


def test_get_all_services_should_return_in_created_order(notify_db_session):
    create_service(service_name='service 1', email_from='service.1')
    create_service(service_name='service 2', email_from='service.2')
    create_service(service_name='service 3', email_from='service.3')
    create_service(service_name='service 4', email_from='service.4')
    assert len(dao_fetch_all_services()) == 4
    assert dao_fetch_all_services()[0].name == 'service 1'
    assert dao_fetch_all_services()[1].name == 'service 2'
    assert dao_fetch_all_services()[2].name == 'service 3'
    assert dao_fetch_all_services()[3].name == 'service 4'


def test_get_all_services_should_return_empty_list_if_no_services():
    assert len(dao_fetch_all_services()) == 0


def test_get_all_services_for_user(notify_db_session):
    user = create_user()
    create_service(service_name='service 1', user=user, email_from='service.1')
    create_service(service_name='service 2', user=user, email_from='service.2')
    create_service(service_name='service 3', user=user, email_from='service.3')
    assert len(dao_fetch_all_services_by_user(user.id)) == 3
    assert dao_fetch_all_services_by_user(user.id)[0].name == 'service 1'
    assert dao_fetch_all_services_by_user(user.id)[1].name == 'service 2'
    assert dao_fetch_all_services_by_user(user.id)[2].name == 'service 3'


def test_get_all_only_services_user_has_access_to(notify_db_session):
    user = create_user()
    create_service(service_name='service 1', user=user, email_from='service.1')
    create_service(service_name='service 2', user=user, email_from='service.2')
    service_3 = create_service(service_name='service 3', user=user, email_from='service.3')
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    dao_add_user_to_service(service_3, new_user)
    assert len(dao_fetch_all_services_by_user(user.id)) == 3
    assert dao_fetch_all_services_by_user(user.id)[0].name == 'service 1'
    assert dao_fetch_all_services_by_user(user.id)[1].name == 'service 2'
    assert dao_fetch_all_services_by_user(user.id)[2].name == 'service 3'
    assert len(dao_fetch_all_services_by_user(new_user.id)) == 1
    assert dao_fetch_all_services_by_user(new_user.id)[0].name == 'service 3'


def test_get_all_user_services_should_return_empty_list_if_no_services_for_user(notify_db_session):
    user = create_user()
    assert len(dao_fetch_all_services_by_user(user.id)) == 0


def test_get_service_by_id_returns_none_if_no_service(notify_db):
    with pytest.raises(NoResultFound) as e:
        dao_fetch_service_by_id(str(uuid.uuid4()))
    assert 'No row was found for one()' in str(e)


def test_get_service_by_id_returns_service(notify_db_session):
    service = create_service(service_name='testing', email_from='testing')
    assert dao_fetch_service_by_id(service.id).name == 'testing'


def test_create_service_returns_service_with_default_permissions(notify_db_session):
    service = create_service(service_name='testing', email_from='testing', service_permissions=None)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(service.permissions, (
        SMS_TYPE, EMAIL_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE,
    ))


@pytest.mark.parametrize("permission_to_remove, permission_remaining", [
    (SMS_TYPE, (EMAIL_TYPE, LETTER_TYPE)),
    (EMAIL_TYPE, (SMS_TYPE, LETTER_TYPE)),
])
def test_remove_permission_from_service_by_id_returns_service_with_correct_permissions(
        notify_db_session, permission_to_remove, permission_remaining
):
    service = create_service(service_permissions=None)
    dao_remove_service_permission(service_id=service.id, permission=permission_to_remove)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(service.permissions, (
        permission_remaining + (INTERNATIONAL_SMS_TYPE,)
    ))


def test_removing_all_permission_returns_service_with_no_permissions(notify_db_session):
    service = create_service()
    dao_remove_service_permission(service_id=service.id, permission=SMS_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=EMAIL_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=INTERNATIONAL_SMS_TYPE)

    service = dao_fetch_service_by_id(service.id)
    assert len(service.permissions) == 0


def test_remove_service_does_not_remove_service_permission_types(notify_db_session):
    service = create_service()
    delete_service_and_all_associated_db_objects(service)

    services = dao_fetch_all_services()
    assert len(services) == 0
    assert set(p.name for p in ServicePermissionTypes.query.all()) == set(SERVICE_PERMISSION_TYPES)


def test_create_service_by_id_adding_and_removing_letter_returns_service_without_letter(service_factory):
    service = service_factory.get('testing', email_from='testing')

    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    dao_add_service_permission(service_id=service.id, permission=LETTER_TYPE)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(service.permissions, (
        SMS_TYPE, EMAIL_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE,
    ))

    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    service = dao_fetch_service_by_id(service.id)

    _assert_service_permissions(service.permissions, (
        SMS_TYPE, EMAIL_TYPE, INTERNATIONAL_SMS_TYPE,
    ))


def test_create_service_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      created_by=user)
    dao_create_service(service, user)
    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 1

    service_from_db = Service.query.first()
    service_history = Service.get_history_model().query.first()

    assert service_from_db.id == service_history.id
    assert service_from_db.name == service_history.name
    assert service_from_db.version == 1
    assert service_from_db.version == service_history.version
    assert service_from_db.postage == 'second'
    assert user.id == service_history.created_by_id
    assert service_from_db.created_by.id == service_history.created_by_id
    assert service_from_db.dvla_organisation_id == DVLA_ORG_HM_GOVERNMENT
    assert service_history.dvla_organisation_id == DVLA_ORG_HM_GOVERNMENT
    assert service_history.postage == 'second'


def test_update_service_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      created_by=user)
    dao_create_service(service, user)

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


def test_update_service_permission_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      created_by=user)
    dao_create_service(service, user, service_permissions=[
        SMS_TYPE,
        EMAIL_TYPE,
        INTERNATIONAL_SMS_TYPE,
    ])

    service.permissions.append(ServicePermission(service_id=service.id, permission='letter'))
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 2

    service_from_db = Service.query.first()

    assert service_from_db.version == 2

    _assert_service_permissions(service.permissions, (
        SMS_TYPE, EMAIL_TYPE, INTERNATIONAL_SMS_TYPE, LETTER_TYPE,
    ))

    permission = [p for p in service.permissions if p.permission == 'sms'][0]
    service.permissions.remove(permission)
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 3

    service_from_db = Service.query.first()
    assert service_from_db.version == 3
    _assert_service_permissions(service.permissions, (
        EMAIL_TYPE, INTERNATIONAL_SMS_TYPE, LETTER_TYPE,
    ))

    assert len(Service.get_history_model().query.filter_by(name='service_name').all()) == 3
    assert Service.get_history_model().query.filter_by(name='service_name').all()[2].version == 3


def test_service_postage_constraint_on_create(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="service_name",
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      created_by=user,
                      postage='third')
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_create_service(service, user)


def test_service_postage_constraint_on_update(notify_db_session):
    create_service()
    service_from_db = Service.query.first()
    service_from_db.postage = 'third'
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_update_service(service_from_db)


def test_create_service_and_history_is_transactional(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name=None,
                      email_from="email_from",
                      message_limit=1000,
                      restricted=False,
                      created_by=user)

    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service, user)

    assert 'column "name" violates not-null constraint' in str(excinfo.value)
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0


def test_delete_service_and_associated_objects(notify_db_session):
    user = create_user()
    service = create_service(user=user, service_permissions=None)
    create_user_code(user=user, code='somecode', code_type='email')
    create_user_code(user=user, code='somecode', code_type='sms')
    template = create_template(service=service)
    api_key = create_api_key(service=service)
    create_notification(template=template, api_key=api_key)
    create_invited_user(service=service)

    assert ServicePermission.query.count() == len((
        SMS_TYPE, EMAIL_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE
    ))

    delete_service_and_all_associated_db_objects(service)
    assert VerifyCode.query.count() == 0
    assert ApiKey.query.count() == 0
    assert ApiKey.get_history_model().query.count() == 0
    assert Template.query.count() == 0
    assert TemplateHistory.query.count() == 0
    assert Job.query.count() == 0
    assert Notification.query.count() == 0
    assert Permission.query.count() == 0
    assert User.query.count() == 0
    assert InvitedUser.query.count() == 0
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    assert ServicePermission.query.count() == 0


def test_add_existing_user_to_another_service_doesnot_change_old_permissions(notify_db_session):
    user = create_user()

    service_one = Service(name="service_one",
                          email_from="service_one",
                          message_limit=1000,
                          restricted=False,
                          created_by=user)

    dao_create_service(service_one, user)
    assert user.id == service_one.users[0].id
    test_user_permissions = Permission.query.filter_by(service=service_one, user=user).all()
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


def test_fetch_stats_filters_on_service(notify_db_session):
    service_one = create_service()
    create_notification(template=create_template(service=service_one))

    service_two = Service(name="service_two",
                          created_by=service_one.created_by,
                          email_from="hello",
                          restricted=False,
                          message_limit=1000)
    dao_create_service(service_two, service_one.created_by)

    stats = dao_fetch_stats_for_service(service_two.id, 7)
    assert len(stats) == 0


def test_fetch_stats_ignores_historical_notification_data(notify_db_session):
    notification = create_notification(template=create_template(service=create_service()))
    service_id = notification.service.id

    db.session.delete(notification)

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 1

    stats = dao_fetch_stats_for_service(service_id, 7)
    assert len(stats) == 0


def test_fetch_stats_counts_correctly(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service)
    email_template = create_template(service=service, template_type='email')
    # two created email, one failed email, and one created sms
    create_notification(template=email_template, status='created')
    create_notification(template=email_template, status='created')
    create_notification(template=email_template, status='technical-failure')
    create_notification(template=sms_template, status='created')

    stats = dao_fetch_stats_for_service(sms_template.service_id, 7)
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


def test_fetch_stats_counts_should_ignore_team_key(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    live_api_key = create_api_key(service=service, key_type=KEY_TYPE_NORMAL)
    team_api_key = create_api_key(service=service, key_type=KEY_TYPE_TEAM)
    test_api_key = create_api_key(service=service, key_type=KEY_TYPE_TEST)

    # two created email, one failed email, and one created sms
    create_notification(template=template, api_key=live_api_key, key_type=live_api_key.key_type)
    create_notification(template=template, api_key=test_api_key, key_type=test_api_key.key_type)
    create_notification(template=template, api_key=team_api_key, key_type=team_api_key.key_type)
    create_notification(template=template)

    stats = dao_fetch_stats_for_service(template.service_id, 7)
    assert len(stats) == 1
    assert stats[0].notification_type == 'sms'
    assert stats[0].status == 'created'
    assert stats[0].count == 3


def test_fetch_stats_for_today_only_includes_today(notify_db_session):
    template = create_template(service=create_service())
    # two created email, one failed email, and one created sms
    with freeze_time('2001-01-01T23:59:00'):
        # just_before_midnight_yesterday
        create_notification(template=template, to_field='1', status='delivered')

    with freeze_time('2001-01-02T00:01:00'):
        # just_after_midnight_today
        create_notification(template=template, to_field='2', status='failed')

    with freeze_time('2001-01-02T12:00:00'):
        # right_now
        create_notification(template=template, to_field='3', status='created')

        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert 'delivered' not in stats
    assert stats['failed'] == 1
    assert stats['created'] == 1


@pytest.mark.parametrize('created_at, limit_days, rows_returned', [
    ('Sunday 8th July 2018 12:00', 7, 0),
    ('Sunday 8th July 2018 22:59', 7, 0),
    ('Sunday 1th July 2018 12:00', 10, 0),
    ('Sunday 8th July 2018 23:00', 7, 1),
    ('Monday 9th July 2018 09:00', 7, 1),
    ('Monday 9th July 2018 15:00', 7, 1),
    ('Monday 16th July 2018 12:00', 7, 1),
    ('Sunday 8th July 2018 12:00', 10, 1),
])
def test_fetch_stats_should_not_gather_notifications_older_than_7_days(
        sample_template, created_at, limit_days, rows_returned
):
    # It's monday today. Things made last monday should still show
    with freeze_time(created_at):
        create_notification(sample_template, )

    with freeze_time('Monday 16th July 2018 12:00'):
        stats = dao_fetch_stats_for_service(sample_template.service_id, limit_days)

    assert len(stats) == rows_returned


def test_dao_fetch_todays_total_message_count_returns_count_for_today(notify_db_session):
    notification = create_notification(template=create_template(service=create_service()))
    assert fetch_todays_total_message_count(notification.service.id) == 1


def test_dao_fetch_todays_total_message_count_returns_0_when_no_messages_for_today(notify_db,
                                                                                   notify_db_session):
    assert fetch_todays_total_message_count(uuid.uuid4()) == 0


def test_dao_fetch_todays_stats_for_all_services_includes_all_services(notify_db_session):
    # two services, each with an email and sms notification
    service1 = create_service(service_name='service 1', email_from='service.1')
    service2 = create_service(service_name='service 2', email_from='service.2')
    template_email_one = create_template(service=service1, template_type='email')
    template_sms_one = create_template(service=service1, template_type='sms')
    template_email_two = create_template(service=service2, template_type='email')
    template_sms_two = create_template(service=service2, template_type='sms')
    create_notification(template=template_email_one)
    create_notification(template=template_sms_one)
    create_notification(template=template_email_two)
    create_notification(template=template_sms_two)

    stats = dao_fetch_todays_stats_for_all_services()

    assert len(stats) == 4
    # services are ordered by service id; not explicit on email/sms or status
    assert stats == sorted(stats, key=lambda x: x.service_id)


def test_dao_fetch_todays_stats_for_all_services_only_includes_today(notify_db_session):
    template = create_template(service=create_service())
    with freeze_time('2001-01-01T23:59:00'):
        # just_before_midnight_yesterday
        create_notification(template=template, to_field='1', status='delivered')

    with freeze_time('2001-01-02T00:01:00'):
        # just_after_midnight_today
        create_notification(template=template, to_field='2', status='failed')

    with freeze_time('2001-01-02T12:00:00'):
        stats = dao_fetch_todays_stats_for_all_services()

    stats = {row.status: row.count for row in stats}
    assert 'delivered' not in stats
    assert stats['failed'] == 1


def test_dao_fetch_todays_stats_for_all_services_groups_correctly(notify_db, notify_db_session):
    service1 = create_service(service_name='service 1', email_from='service.1')
    service2 = create_service(service_name='service 2', email_from='service.2')
    template_sms = create_template(service=service1)
    template_email = create_template(service=service1, template_type='email')
    template_two = create_template(service=service2)
    # service1: 2 sms with status "created" and one "failed", and one email
    create_notification(template=template_sms)
    create_notification(template=template_sms)
    create_notification(template=template_sms, status='failed')
    create_notification(template=template_email)
    # service2: 1 sms "created"
    create_notification(template=template_two)

    stats = dao_fetch_todays_stats_for_all_services()
    assert len(stats) == 4
    assert (service1.id, service1.name, service1.restricted, service1.research_mode, service1.active,
            service1.created_at, 'sms', 'created', 2) in stats
    assert (service1.id, service1.name, service1.restricted, service1.research_mode, service1.active,
            service1.created_at, 'sms', 'failed', 1) in stats
    assert (service1.id, service1.name, service1.restricted, service1.research_mode, service1.active,
            service1.created_at, 'email', 'created', 1) in stats
    assert (service2.id, service2.name, service2.restricted, service2.research_mode, service2.active,
            service2.created_at, 'sms', 'created', 1) in stats


def test_dao_fetch_todays_stats_for_all_services_includes_all_keys_by_default(notify_db_session):
    template = create_template(service=create_service())
    create_notification(template=template, key_type=KEY_TYPE_NORMAL)
    create_notification(template=template, key_type=KEY_TYPE_TEAM)
    create_notification(template=template, key_type=KEY_TYPE_TEST)

    stats = dao_fetch_todays_stats_for_all_services()

    assert len(stats) == 1
    assert stats[0].count == 3


def test_dao_fetch_todays_stats_for_all_services_can_exclude_from_test_key(notify_db_session):
    template = create_template(service=create_service())
    create_notification(template=template, key_type=KEY_TYPE_NORMAL)
    create_notification(template=template, key_type=KEY_TYPE_TEAM)
    create_notification(template=template, key_type=KEY_TYPE_TEST)

    stats = dao_fetch_todays_stats_for_all_services(include_from_test_key=False)

    assert len(stats) == 1
    assert stats[0].count == 2


def test_fetch_stats_by_date_range_for_all_services(notify_db_session):
    template = create_template(service=create_service())
    create_notification(template=template, created_at=datetime.now() - timedelta(days=4))
    create_notification(template=template, created_at=datetime.now() - timedelta(days=3))
    result_one = create_notification(template=template, created_at=datetime.now() - timedelta(days=2))
    create_notification(template=template, created_at=datetime.now() - timedelta(days=1))
    create_notification(template=template, created_at=datetime.now())

    start_date = (datetime.utcnow() - timedelta(days=2)).date()
    end_date = (datetime.utcnow() - timedelta(days=1)).date()

    results = fetch_stats_by_date_range_for_all_services(start_date, end_date)

    assert len(results) == 1
    assert results[0] == (result_one.service.id, result_one.service.name, result_one.service.restricted,
                          result_one.service.research_mode, result_one.service.active,
                          result_one.service.created_at, 'sms', 'created', 2)


@freeze_time('2001-01-01T23:59:00')
def test_dao_suspend_service_marks_service_as_inactive_and_expires_api_keys(notify_db_session):
    service = create_service()
    api_key = create_api_key(service=service)
    dao_suspend_service(service.id)
    service = Service.query.get(service.id)
    assert not service.active
    assert service.name == service.name

    api_key = ApiKey.query.get(api_key.id)
    assert api_key.expiry_date == datetime(2001, 1, 1, 23, 59, 00)


@pytest.mark.parametrize("start_delta, end_delta, expected",
                         [("5", "1", "4"),  # a date range less than 7 days ago returns test and normal notifications
                          ("9", "8", "1"),  # a date range older than 9 days does not return test notifications.
                          ("8", "4", "2")])  # a date range that starts more than 7 days ago
@freeze_time('2017-10-23T00:00:00')
def test_fetch_stats_by_date_range_for_all_services_returns_test_notifications(notify_db_session,
                                                                               start_delta,
                                                                               end_delta,
                                                                               expected):
    template = create_template(service=create_service())
    result_one = create_notification(template=template, created_at=datetime.now(), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=2), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=3), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=4), key_type='normal')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=4), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=8), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=8), key_type='normal')

    start_date = (datetime.utcnow() - timedelta(days=int(start_delta))).date()
    end_date = (datetime.utcnow() - timedelta(days=int(end_delta))).date()

    results = fetch_stats_by_date_range_for_all_services(start_date, end_date, include_from_test_key=True)

    assert len(results) == 1
    assert results[0] == (result_one.service.id, result_one.service.name, result_one.service.restricted,
                          result_one.service.research_mode, result_one.service.active, result_one.service.created_at,
                          'sms', 'created', int(expected))


@pytest.mark.parametrize("start_delta, end_delta, expected",
                         [("5", "1", "4"),  # a date range less than 7 days ago returns test and normal notifications
                          ("9", "8", "1"),  # a date range older than 9 days does not return test notifications.
                          ("8", "4", "2")])  # a date range that starts more than 7 days ago
@freeze_time('2017-10-23T23:00:00')
def test_fetch_stats_by_date_range_during_bst_hour_for_all_services_returns_test_notifications(
        notify_db_session, start_delta, end_delta, expected
):
    template = create_template(service=create_service())
    result_one = create_notification(template=template, created_at=datetime.now(), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=2), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=3), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=4), key_type='normal')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=4), key_type='test')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=8), key_type='normal')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=9), key_type='normal')
    create_notification(template=template, created_at=datetime.now() - timedelta(days=9), key_type='test')

    start_date = (datetime.utcnow() - timedelta(days=int(start_delta))).date()
    end_date = (datetime.utcnow() - timedelta(days=int(end_delta))).date()

    results = fetch_stats_by_date_range_for_all_services(start_date, end_date, include_from_test_key=True)

    assert len(results) == 1
    assert results[0] == (result_one.service.id, result_one.service.name, result_one.service.restricted,
                          result_one.service.research_mode, result_one.service.active, result_one.service.created_at,
                          'sms', 'created', int(expected))


@freeze_time('2001-01-01T23:59:00')
def test_dao_resume_service_marks_service_as_active_and_api_keys_are_still_revoked(notify_db_session):
    service = create_service()
    api_key = create_api_key(service=service)
    dao_suspend_service(service.id)
    service = Service.query.get(service.id)
    assert not service.active

    dao_resume_service(service.id)
    assert Service.query.get(service.id).active

    api_key = ApiKey.query.get(api_key.id)
    assert api_key.expiry_date == datetime(2001, 1, 1, 23, 59, 00)


def test_dao_fetch_active_users_for_service_returns_active_only(notify_db_session):
    active_user = create_user(email='active@foo.com', state='active')
    pending_user = create_user(email='pending@foo.com', state='pending')
    service = create_service(user=active_user)
    dao_add_user_to_service(service, pending_user)
    users = dao_fetch_active_users_for_service(service.id)

    assert len(users) == 1


def test_dao_fetch_service_by_inbound_number_with_inbound_number(notify_db_session):
    foo1 = create_service_with_inbound_number(service_name='a', inbound_number='1')
    create_service_with_defined_sms_sender(service_name='b', sms_sender_value='2')
    create_service_with_defined_sms_sender(service_name='c', sms_sender_value='3')
    create_inbound_number('2')
    create_inbound_number('3')

    service = dao_fetch_service_by_inbound_number('1')

    assert foo1.id == service.id


def test_dao_fetch_service_by_inbound_number_with_inbound_number_not_set(notify_db_session):
    create_inbound_number('1')

    service = dao_fetch_service_by_inbound_number('1')

    assert service is None


def test_dao_fetch_service_by_inbound_number_when_inbound_number_set(notify_db_session):
    service_1 = create_service_with_inbound_number(inbound_number='1', service_name='a')
    create_service(service_name='b')

    service = dao_fetch_service_by_inbound_number('1')

    assert service.id == service_1.id


def test_dao_fetch_service_by_inbound_number_with_unknown_number(notify_db_session):
    create_service_with_inbound_number(inbound_number='1', service_name='a')

    service = dao_fetch_service_by_inbound_number('9')

    assert service is None


def test_dao_fetch_service_by_inbound_number_with_inactive_number_returns_empty(notify_db_session):
    service = create_service_with_inbound_number(inbound_number='1', service_name='a')
    dao_set_inbound_number_active_flag(service_id=service.id, active=False)

    service = dao_fetch_service_by_inbound_number('1')

    assert service is None


def test_dao_allocating_inbound_number_shows_on_service(notify_db_session):
    create_service_with_inbound_number()
    create_inbound_number(number='07700900003')

    inbound_numbers = dao_get_available_inbound_numbers()

    service = create_service(service_name='test service')

    dao_set_inbound_number_to_service(service.id, inbound_numbers[0])

    assert service.inbound_number.number == inbound_numbers[0].number


def _assert_service_permissions(service_permissions, expected):
    assert len(service_permissions) == len(expected)
    assert set(expected) == set(p.permission for p in service_permissions)


def test_dao_fetch_monthly_historical_stats_by_template(notify_db_session):
    service = create_service()
    template_one = create_template(service=service, template_name='1')
    template_two = create_template(service=service, template_name='2')

    create_notification(created_at=datetime(2017, 10, 1), template=template_one, status='delivered')
    create_notification(created_at=datetime(2016, 4, 1), template=template_two, status='delivered')
    create_notification(created_at=datetime(2016, 4, 1), template=template_two, status='delivered')
    create_notification(created_at=datetime.now(), template=template_two, status='delivered')

    result = sorted(dao_fetch_monthly_historical_stats_by_template(), key=lambda x: (x.month, x.year))

    assert len(result) == 2

    assert result[0].template_id == template_two.id
    assert result[0].month == 4
    assert result[0].year == 2016
    assert result[0].count == 2

    assert result[1].template_id == template_one.id
    assert result[1].month == 10
    assert result[1].year == 2017
    assert result[1].count == 1


def test_dao_fetch_monthly_historical_usage_by_template_for_service_no_stats_today(
        notify_db_session,
):
    service = create_service()
    template_one = create_template(service=service, template_name='1')
    template_two = create_template(service=service, template_name='2')

    n = create_notification(created_at=datetime(2017, 10, 1), template=template_one, status='delivered')
    create_notification(created_at=datetime(2017, 4, 1), template=template_two, status='delivered')
    create_notification(created_at=datetime(2017, 4, 1), template=template_two, status='delivered')
    create_notification(created_at=datetime.now(), template=template_two, status='delivered')

    daily_stats_template_usage_by_month()

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 2

    assert result[0].template_id == template_two.id
    assert result[0].name == template_two.name
    assert result[0].template_type == template_two.template_type
    assert result[0].month == 4
    assert result[0].year == 2017
    assert result[0].count == 2

    assert result[1].template_id == template_one.id
    assert result[1].name == template_one.name
    assert result[1].template_type == template_two.template_type
    assert result[1].month == 10
    assert result[1].year == 2017
    assert result[1].count == 1


@freeze_time("2017-11-10 11:09:00.000000")
def test_dao_fetch_monthly_historical_usage_by_template_for_service_add_to_historical(
        notify_db_session,
):
    service = create_service()
    template_one = create_template(service=service, template_name='1')
    template_two = create_template(service=service, template_name='2')
    template_three = create_template(service=service, template_name='3')

    date = datetime.now()
    day = date.day
    month = date.month
    year = date.year

    n = create_notification(created_at=datetime(2017, 9, 1), template=template_one, status='delivered')
    create_notification(created_at=datetime(year, month, day) - timedelta(days=1), template=template_two,
                        status='delivered')
    create_notification(created_at=datetime(year, month, day) - timedelta(days=1), template=template_two,
                        status='delivered')

    daily_stats_template_usage_by_month()

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 2

    assert result[0].template_id == template_one.id
    assert result[0].name == template_one.name
    assert result[0].template_type == template_one.template_type
    assert result[0].month == 9
    assert result[0].year == 2017
    assert result[0].count == 1

    assert result[1].template_id == template_two.id
    assert result[1].name == template_two.name
    assert result[1].template_type == template_two.template_type
    assert result[1].month == 11
    assert result[1].year == 2017
    assert result[1].count == 2

    create_notification(
        template=template_three,
        created_at=datetime.now(),
        status='delivered'
    )
    create_notification(
        template=template_two,
        created_at=datetime.now(),
        status='delivered'
    )

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 3

    assert result[0].template_id == template_one.id
    assert result[0].name == template_one.name
    assert result[0].template_type == template_one.template_type
    assert result[0].month == 9
    assert result[0].year == 2017
    assert result[0].count == 1

    assert result[1].template_id == template_two.id
    assert result[1].name == template_two.name
    assert result[1].template_type == template_two.template_type
    assert result[1].month == month
    assert result[1].year == year
    assert result[1].count == 3

    assert result[2].template_id == template_three.id
    assert result[2].name == template_three.name
    assert result[2].template_type == template_three.template_type
    assert result[2].month == 11
    assert result[2].year == 2017
    assert result[2].count == 1


@freeze_time("2017-11-10 11:09:00.000000")
def test_dao_fetch_monthly_historical_usage_by_template_for_service_does_add_old_notification(
        notify_db_session,
):
    template_one, template_three, template_two = create_email_sms_letter_template()

    date = datetime.now()
    day = date.day
    month = date.month
    year = date.year

    n = create_notification(created_at=datetime(2017, 9, 1), template=template_one, status='delivered')
    create_notification(created_at=datetime(year, month, day) - timedelta(days=1), template=template_two,
                        status='delivered')
    create_notification(created_at=datetime(year, month, day) - timedelta(days=1), template=template_two,
                        status='delivered')

    daily_stats_template_usage_by_month()

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 2

    assert result[0].template_id == template_one.id
    assert result[0].name == template_one.name
    assert result[0].template_type == template_one.template_type
    assert result[0].month == 9
    assert result[0].year == 2017
    assert result[0].count == 1

    assert result[1].template_id == template_two.id
    assert result[1].name == template_two.name
    assert result[1].template_type == template_two.template_type
    assert result[1].month == 11
    assert result[1].year == 2017
    assert result[1].count == 2

    create_notification(
        template=template_three,
        created_at=datetime.utcnow() - timedelta(days=2),
        status='delivered'
    )

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 2


@freeze_time("2017-11-10 11:09:00.000000")
def test_dao_fetch_monthly_historical_usage_by_template_for_service_get_this_year_only(
        notify_db_session,
):
    template_one, template_three, template_two = create_email_sms_letter_template()

    date = datetime.now()
    day = date.day
    month = date.month
    year = date.year

    n = create_notification(created_at=datetime(2016, 9, 1), template=template_one, status='delivered')
    create_notification(created_at=datetime(year, month, day) - timedelta(days=1), template=template_two,
                        status='delivered')
    create_notification(created_at=datetime(year, month, day) - timedelta(days=1), template=template_two,
                        status='delivered')

    daily_stats_template_usage_by_month()

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 1

    assert result[0].template_id == template_two.id
    assert result[0].name == template_two.name
    assert result[0].template_type == template_two.template_type
    assert result[0].month == 11
    assert result[0].year == 2017
    assert result[0].count == 2

    create_notification(
        template=template_three,
        created_at=datetime.utcnow() - timedelta(days=2)
    )

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 1

    create_notification(
        template=template_three,
        created_at=datetime.utcnow()
    )

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 2


def create_email_sms_letter_template():
    service = create_service()
    template_one = create_template(service=service, template_name='1', template_type='email')
    template_two = create_template(service=service, template_name='2', template_type='sms')
    template_three = create_template(service=service, template_name='3', template_type='letter')
    return template_one, template_three, template_two


@freeze_time("2017-11-10 11:09:00.000000")
def test_dao_fetch_monthly_historical_usage_by_template_for_service_combined_historical_current(
        notify_db_session,
):
    template_one = create_template(service=create_service(), template_name='1')

    date = datetime.now()
    day = date.day
    month = date.month
    year = date.year

    n = create_notification(status='delivered', created_at=datetime(year, month, day) - timedelta(days=30),
                            template=template_one)

    daily_stats_template_usage_by_month()

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 1

    assert result[0].template_id == template_one.id
    assert result[0].name == template_one.name
    assert result[0].template_type == template_one.template_type
    assert result[0].month == 10
    assert result[0].year == 2017
    assert result[0].count == 1

    create_notification(
        template=template_one,
        created_at=datetime.utcnow()
    )

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 2

    assert result[0].template_id == template_one.id
    assert result[0].name == template_one.name
    assert result[0].template_type == template_one.template_type
    assert result[0].month == 10
    assert result[0].year == 2017
    assert result[0].count == 1

    assert result[1].template_id == template_one.id
    assert result[1].name == template_one.name
    assert result[1].template_type == template_one.template_type
    assert result[1].month == 11
    assert result[1].year == 2017
    assert result[1].count == 1


@freeze_time("2017-11-10 11:09:00.000000")
def test_dao_fetch_monthly_historical_usage_by_template_for_service_does_not_return_double_precision_values(
        notify_db_session,
):
    template_one = create_template(service=create_service())

    n = create_notification(
        template=template_one,
        created_at=datetime.utcnow()
    )

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.month, x.year)
    )

    assert len(result) == 1

    assert result[0].template_id == template_one.id
    assert result[0].name == template_one.name
    assert result[0].template_type == template_one.template_type
    assert result[0].month == 11
    assert len(str(result[0].month)) == 2
    assert result[0].year == 2017
    assert len(str(result[0].year)) == 4
    assert result[0].count == 1


@freeze_time("2018-03-10 11:09:00.000000")
def test_dao_fetch_monthly_historical_usage_by_template_for_service_returns_financial_year(
        notify_db,
        notify_db_session,
):
    service = create_service()
    template_one = create_template(service=service, template_name='1', template_type='email')

    date = datetime.now()
    day = date.day
    year = date.year

    create_notification(template=template_one, status='delivered', created_at=datetime(year - 1, 1, day))
    create_notification(template=template_one, status='delivered', created_at=datetime(year - 1, 3, day))
    create_notification(template=template_one, status='delivered', created_at=datetime(year - 1, 4, day))
    create_notification(template=template_one, status='delivered', created_at=datetime(year - 1, 5, day))
    create_notification(template=template_one, status='delivered', created_at=datetime(year, 1, day))
    create_notification(template=template_one, status='delivered', created_at=datetime(year, 2, day))

    daily_stats_template_usage_by_month()

    n = create_notification(
        template=template_one,
        created_at=datetime.utcnow()
    )

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2017),
        key=lambda x: (x.year, x.month)
    )

    assert len(result) == 5

    assert result[0].month == 4
    assert result[0].year == 2017
    assert result[1].month == 5
    assert result[1].year == 2017
    assert result[2].month == 1
    assert result[2].year == 2018
    assert result[3].month == 2
    assert result[3].year == 2018
    assert result[4].month == 3
    assert result[4].year == 2018

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(n.service_id, 2014),
        key=lambda x: (x.year, x.month)
    )

    assert len(result) == 0


@freeze_time("2018-03-10 11:09:00.000000")
def test_dao_fetch_monthly_historical_usage_by_template_for_service_only_returns_for_service(
        notify_db_session
):
    template_one = create_template(service=create_service(), template_name='1', template_type='email')

    date = datetime.now()
    day = date.day
    year = date.year

    create_notification(template=template_one, created_at=datetime(year, 1, day))
    create_notification(template=template_one, created_at=datetime(year, 2, day))
    create_notification(template=template_one, created_at=datetime(year, 3, day))

    service_two = create_service(service_name='other_service', user=create_user())
    template_two = create_template(service=service_two, template_name='1', template_type='email')

    create_notification(template=template_two)
    create_notification(template=template_two)

    daily_stats_template_usage_by_month()

    x = dao_fetch_monthly_historical_usage_by_template_for_service(template_one.service_id, 2017)

    result = sorted(
        x,
        key=lambda x: (x.year, x.month)
    )

    assert len(result) == 3

    result = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(service_two.id, 2017),
        key=lambda x: (x.year, x.month)
    )

    assert len(result) == 1


@freeze_time("2018-01-01 11:09:00.000000")
def test_dao_fetch_monthly_historical_usage_by_template_for_service_ignores_test_api_keys(notify_db_session):
    service = create_service()
    template_1 = create_template(service, template_name='1')
    template_2 = create_template(service, template_name='2')
    template_3 = create_template(service, template_name='3')

    create_notification(template_1, key_type=KEY_TYPE_TEST)
    create_notification(template_2, key_type=KEY_TYPE_TEAM)
    create_notification(template_3, key_type=KEY_TYPE_NORMAL)

    results = sorted(
        dao_fetch_monthly_historical_usage_by_template_for_service(service.id, 2017),
        key=lambda x: x.name
    )

    assert len(results) == 2
    # template_1 only used with test keys
    assert results[0].template_id == template_2.id
    assert results[0].count == 1

    assert results[1].template_id == template_3.id
    assert results[1].count == 1
