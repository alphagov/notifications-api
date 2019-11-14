import pytest

from datetime import datetime
from freezegun import freeze_time
from sqlalchemy.sql import desc

from app.models import ProviderDetails, ProviderDetailsHistory
from app import clients
from app.dao.provider_details_dao import (
    get_alternative_sms_provider,
    get_provider_details_by_identifier,
    get_provider_details_by_notification_type,
    dao_update_provider_details,
    dao_get_provider_stats,
    dao_reduce_sms_provider_priority,
)
from tests.app.db import (
    create_ft_billing,
    create_service,
    create_template,
)


def set_primary_sms_provider(identifier):
    primary_provider = get_provider_details_by_identifier(identifier)
    secondary_provider = get_provider_details_by_identifier(get_alternative_sms_provider(identifier))

    primary_provider.priority = 10
    secondary_provider.priority = 20

    dao_update_provider_details(primary_provider)
    dao_update_provider_details(secondary_provider)


def test_can_get_sms_non_international_providers(notify_db_session):
    sms_providers = get_provider_details_by_notification_type('sms')
    assert len(sms_providers) == 2
    assert all('sms' == prov.notification_type for prov in sms_providers)


def test_can_get_sms_international_providers(notify_db_session):
    sms_providers = get_provider_details_by_notification_type('sms', True)
    assert len(sms_providers) == 1
    assert all('sms' == prov.notification_type for prov in sms_providers)
    assert all(prov.supports_international for prov in sms_providers)


def test_can_get_sms_providers_in_order_of_priority(notify_db_session):
    providers = get_provider_details_by_notification_type('sms', False)

    assert providers[0].priority < providers[1].priority


def test_can_get_email_providers_in_order_of_priority(notify_db_session):
    providers = get_provider_details_by_notification_type('email')

    assert providers[0].identifier == "ses"


def test_can_get_email_providers(notify_db_session):
    assert len(get_provider_details_by_notification_type('email')) == 1
    types = [provider.notification_type for provider in get_provider_details_by_notification_type('email')]
    assert all('email' == notification_type for notification_type in types)


def test_should_not_error_if_any_provider_in_code_not_in_database(restore_provider_details):
    ProviderDetails.query.filter_by(identifier='mmg').delete()

    assert clients.get_sms_client('mmg')


@freeze_time('2000-01-01T00:00:00')
def test_update_adds_history(restore_provider_details):
    ses = ProviderDetails.query.filter(ProviderDetails.identifier == 'ses').one()
    ses_history = ProviderDetailsHistory.query.filter(ProviderDetailsHistory.id == ses.id).one()

    assert ses.version == 1
    assert ses_history.version == 1
    assert ses.updated_at is None

    ses.active = False

    dao_update_provider_details(ses)

    assert not ses.active
    assert ses.updated_at == datetime(2000, 1, 1, 0, 0, 0)

    ses_history = ProviderDetailsHistory.query.filter(
        ProviderDetailsHistory.id == ses.id
    ).order_by(
        ProviderDetailsHistory.version
    ).all()

    assert ses_history[0].active
    assert ses_history[0].version == 1
    assert ses_history[0].updated_at is None

    assert not ses_history[1].active
    assert ses_history[1].version == 2
    assert ses_history[1].updated_at == datetime(2000, 1, 1, 0, 0, 0)


def test_update_sms_provider_to_inactive_sets_inactive(restore_provider_details):
    mmg = get_provider_details_by_identifier('mmg')

    mmg.active = False
    dao_update_provider_details(mmg)

    assert not mmg.active


@pytest.mark.parametrize('identifier, expected', [
    ('firetext', 'mmg'),
    ('mmg', 'firetext'),
])
def test_get_alternative_sms_provider_returns_expected_provider(identifier, expected):
    assert get_alternative_sms_provider(identifier) == expected


def test_get_alternative_sms_provider_fails_if_unrecognised():
    with pytest.raises(ValueError):
        get_alternative_sms_provider('ses')


@pytest.mark.parametrize(['starting_priorities', 'expected_priorities'], [
    ({'mmg': 50, 'firetext': 50}, {'mmg': 40, 'firetext': 60}),
    ({'mmg': 0, 'firetext': 20}, {'mmg': 0, 'firetext': 30}),  # lower bound respected
    ({'mmg': 50, 'firetext': 100}, {'mmg': 40, 'firetext': 100}),  # upper bound respected

    # document what happens if they have unexpected values outside of the 0 - 100 range (due to manual setting from
    # the admin app). the code never causes further issues, but sometimes doesn't actively reset the vaues to 0-100.
    ({'mmg': 150, 'firetext': 50}, {'mmg': 140, 'firetext': 60}),
    ({'mmg': 50, 'firetext': 150}, {'mmg': 40, 'firetext': 100}),

    ({'mmg': -100, 'firetext': 50}, {'mmg': 0, 'firetext': 60}),
    ({'mmg': 50, 'firetext': -100}, {'mmg': 40, 'firetext': -90}),
])
def test_reduce_sms_provider_priority_switches_provider(
    notify_db_session,
    mocker,
    restore_provider_details,
    sample_user,
    starting_priorities,
    expected_priorities,
):
    mocker.patch('app.dao.provider_details_dao.get_user_by_id', return_value=sample_user)
    mmg = get_provider_details_by_identifier('mmg')
    firetext = get_provider_details_by_identifier('firetext')

    mmg.priority = starting_priorities['mmg']
    firetext.priority = starting_priorities['firetext']

    # switch away from mmg. currently both 50/50
    dao_reduce_sms_provider_priority('mmg')

    assert firetext.priority == expected_priorities['firetext']
    assert mmg.priority == expected_priorities['mmg']
    assert mmg.created_by is sample_user
    assert firetext.created_by is sample_user


def test_reduce_sms_provider_priority_adds_rows_to_history_table(
    mocker,
    restore_provider_details,
    sample_user
):
    mocker.patch('app.dao.provider_details_dao.get_user_by_id', return_value=sample_user)
    mmg = get_provider_details_by_identifier('mmg')
    provider_history_rows = ProviderDetailsHistory.query.filter(
        ProviderDetailsHistory.id == mmg.id
    ).order_by(
        desc(ProviderDetailsHistory.version)
    ).all()

    dao_reduce_sms_provider_priority(mmg.identifier)

    updated_provider_history_rows = ProviderDetailsHistory.query.filter(
        ProviderDetailsHistory.id == mmg.id
    ).order_by(
        desc(ProviderDetailsHistory.version)
    ).all()

    assert len(updated_provider_history_rows) - len(provider_history_rows) == 1
    assert updated_provider_history_rows[0].version - provider_history_rows[0].version == 1
    assert updated_provider_history_rows[0].priority == 90


@freeze_time('2017-05-01 14:00:00')
def test_reduce_sms_provider_priority_does_nothing_if_providers_have_recently_changed(
    mocker,
    restore_provider_details,
):
    mock_is_slow = mocker.patch('app.celery.scheduled_tasks.is_delivery_slow_for_providers')
    mock_reduce = mocker.patch('app.celery.scheduled_tasks.dao_reduce_sms_provider_priority')
    get_provider_details_by_identifier('mmg').updated_at = datetime(2017, 5, 1, 13, 51)

    dao_reduce_sms_provider_priority('firetext')

    assert mock_is_slow.called is False
    assert mock_reduce.called is False


@freeze_time('2018-06-28 12:00')
def test_dao_get_provider_stats(notify_db_session):
    service_1 = create_service(service_name='1')
    service_2 = create_service(service_name='2')
    sms_template_1 = create_template(service_1, 'sms')
    sms_template_2 = create_template(service_2, 'sms')

    create_ft_billing('2017-06-05', 'sms', sms_template_2, service_1, provider='firetext', billable_unit=4)
    create_ft_billing('2018-05-31', 'sms', sms_template_1, service_1, provider='mmg', billable_unit=1)
    create_ft_billing('2018-06-01', 'sms', sms_template_1, service_1, provider='mmg',
                      rate_multiplier=2, billable_unit=1)
    create_ft_billing('2018-06-03', 'sms', sms_template_2, service_1, provider='firetext', billable_unit=4)
    create_ft_billing('2018-06-15', 'sms', sms_template_1, service_2, provider='firetext', billable_unit=1)
    create_ft_billing('2018-06-28', 'sms', sms_template_2, service_2, provider='mmg', billable_unit=2)

    result = dao_get_provider_stats()

    assert len(result) == 4

    assert result[0].identifier == 'ses'
    assert result[0].display_name == 'AWS SES'
    assert result[0].created_by_name is None
    assert result[0].current_month_billable_sms == 0

    assert result[1].identifier == 'firetext'
    assert result[1].notification_type == 'sms'
    assert result[1].supports_international is False
    assert result[1].active is True
    assert result[1].current_month_billable_sms == 5

    assert result[2].identifier == 'mmg'
    assert result[2].display_name == 'MMG'
    assert result[2].supports_international is True
    assert result[2].active is True
    assert result[2].current_month_billable_sms == 4

    assert result[3].identifier == 'dvla'
    assert result[3].current_month_billable_sms == 0
    assert result[3].supports_international is False
