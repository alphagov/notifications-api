from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time
from sqlalchemy.sql import desc

from app import notification_provider_clients
from app.dao.provider_details_dao import (
    _adjust_provider_priority,
    _get_sms_providers_for_update,
    dao_adjust_provider_priority_back_to_resting_points,
    dao_get_provider_stats,
    dao_reduce_sms_provider_priority,
    dao_update_provider_details,
    get_alternative_sms_provider,
    get_provider_details_by_identifier,
    get_provider_details_by_notification_type,
)
from app.models import ProviderDetails, ProviderDetailsHistory
from tests.app.db import create_ft_billing, create_service, create_template
from tests.conftest import set_config


@pytest.fixture(autouse=True)
def set_provider_resting_points(notify_api):
    with set_config(notify_api, "SMS_PROVIDER_RESTING_POINTS", {"mmg": 60, "firetext": 40}):
        yield


def set_primary_sms_provider(identifier):
    primary_provider = get_provider_details_by_identifier(identifier)
    secondary_provider = get_provider_details_by_identifier(get_alternative_sms_provider(identifier))

    primary_provider.priority = 10
    secondary_provider.priority = 20

    dao_update_provider_details(primary_provider)
    dao_update_provider_details(secondary_provider)


def test_can_get_sms_non_international_providers(notify_db_session):
    sms_providers = get_provider_details_by_notification_type("sms")
    assert len(sms_providers) > 0
    assert all("sms" == prov.notification_type for prov in sms_providers)


def test_can_get_sms_international_providers(notify_db_session):
    sms_providers = get_provider_details_by_notification_type("sms", True)
    assert len(sms_providers) == 1
    assert all("sms" == prov.notification_type for prov in sms_providers)
    assert all(prov.supports_international for prov in sms_providers)


def test_can_get_sms_providers_in_order_of_priority(notify_db_session):
    providers = get_provider_details_by_notification_type("sms", False)
    priorities = [provider.priority for provider in providers]
    assert priorities == sorted(priorities)


def test_can_get_email_providers_in_order_of_priority(notify_db_session):
    providers = get_provider_details_by_notification_type("email")

    assert providers[0].identifier == "ses"


def test_can_get_email_providers(notify_db_session):
    assert len(get_provider_details_by_notification_type("email")) == 1
    types = [provider.notification_type for provider in get_provider_details_by_notification_type("email")]
    assert all("email" == notification_type for notification_type in types)


def test_should_not_error_if_any_provider_in_code_not_in_database(restore_provider_details):
    ProviderDetails.query.filter_by(identifier="mmg").delete()

    assert notification_provider_clients.get_sms_client("mmg")


@freeze_time("2000-01-01T00:00:00")
def test_update_adds_history(restore_provider_details):
    ses = ProviderDetails.query.filter(ProviderDetails.identifier == "ses").one()
    ses_history = ProviderDetailsHistory.query.filter(ProviderDetailsHistory.id == ses.id).one()

    assert ses.version == 1
    assert ses_history.version == 1
    assert ses.updated_at is None

    ses.active = False

    dao_update_provider_details(ses)

    assert not ses.active
    assert ses.updated_at == datetime(2000, 1, 1, 0, 0, 0)

    ses_history = (
        ProviderDetailsHistory.query.filter(ProviderDetailsHistory.id == ses.id)
        .order_by(ProviderDetailsHistory.version)
        .all()
    )

    assert ses_history[0].active
    assert ses_history[0].version == 1
    assert ses_history[0].updated_at is None

    assert not ses_history[1].active
    assert ses_history[1].version == 2
    assert ses_history[1].updated_at == datetime(2000, 1, 1, 0, 0, 0)


def test_update_sms_provider_to_inactive_sets_inactive(restore_provider_details):
    mmg = get_provider_details_by_identifier("mmg")

    mmg.active = False
    dao_update_provider_details(mmg)

    assert not mmg.active


@pytest.mark.parametrize(
    "identifier, expected",
    [
        ("firetext", "mmg"),
        ("mmg", "firetext"),
    ],
)
def test_get_alternative_sms_provider_returns_expected_provider(identifier, expected):
    assert get_alternative_sms_provider(identifier) == expected


def test_get_alternative_sms_provider_fails_if_unrecognised():
    with pytest.raises(ValueError):
        get_alternative_sms_provider("ses")


@freeze_time("2016-01-01 00:30")
def test_adjust_provider_priority_sets_priority(
    restore_provider_details,
    notify_user,
    mmg_provider,
):
    # need to update these manually to avoid triggering the `onupdate` clause of the updated_at column
    ProviderDetails.query.filter(ProviderDetails.identifier == "mmg").update({"updated_at": datetime.min})

    _adjust_provider_priority(mmg_provider, 50)

    assert mmg_provider.updated_at == datetime.utcnow()
    assert mmg_provider.created_by.id == notify_user.id
    assert mmg_provider.priority == 50


@freeze_time("2016-01-01 00:30")
def test_adjust_provider_priority_adds_history(
    restore_provider_details,
    notify_user,
    mmg_provider,
):
    # need to update these manually to avoid triggering the `onupdate` clause of the updated_at column
    ProviderDetails.query.filter(ProviderDetails.identifier == "mmg").update({"updated_at": datetime.min})

    old_provider_history_rows = (
        ProviderDetailsHistory.query.filter(ProviderDetailsHistory.id == mmg_provider.id)
        .order_by(desc(ProviderDetailsHistory.version))
        .all()
    )

    _adjust_provider_priority(mmg_provider, 50)

    updated_provider_history_rows = (
        ProviderDetailsHistory.query.filter(ProviderDetailsHistory.id == mmg_provider.id)
        .order_by(desc(ProviderDetailsHistory.version))
        .all()
    )

    assert len(updated_provider_history_rows) - len(old_provider_history_rows) == 1
    assert updated_provider_history_rows[0].version - old_provider_history_rows[0].version == 1
    assert updated_provider_history_rows[0].priority == 50


@freeze_time("2016-01-01 01:00")
def test_get_sms_providers_for_update_returns_providers(restore_provider_details):
    sixty_one_minutes_ago = datetime(2015, 12, 31, 23, 59)
    ProviderDetails.query.filter(ProviderDetails.identifier == "mmg").update({"updated_at": sixty_one_minutes_ago})
    ProviderDetails.query.filter(ProviderDetails.identifier == "firetext").update({"updated_at": None})

    resp = _get_sms_providers_for_update(timedelta(hours=1))

    assert {p.identifier for p in resp} == {"mmg", "firetext"}


@freeze_time("2016-01-01 01:00")
def test_get_sms_providers_for_update_returns_nothing_if_recent_updates(restore_provider_details):
    fifty_nine_minutes_ago = datetime(2016, 1, 1, 0, 1)
    ProviderDetails.query.filter(ProviderDetails.identifier == "mmg").update({"updated_at": fifty_nine_minutes_ago})

    resp = _get_sms_providers_for_update(timedelta(hours=1))

    assert not resp


@pytest.mark.parametrize(
    ["starting_priorities", "expected_priorities"],
    [
        ({"mmg": 50, "firetext": 50}, {"mmg": 40, "firetext": 60}),
        ({"mmg": 0, "firetext": 20}, {"mmg": 0, "firetext": 30}),  # lower bound respected
        ({"mmg": 50, "firetext": 100}, {"mmg": 40, "firetext": 100}),  # upper bound respected
        # document what happens if they have unexpected values outside of the 0 - 100 range (due to manual setting from
        # the admin app). the code never causes further issues, but sometimes doesn't actively reset the vaues to 0-100.
        ({"mmg": 150, "firetext": 50}, {"mmg": 140, "firetext": 60}),
        ({"mmg": 50, "firetext": 150}, {"mmg": 40, "firetext": 100}),
        ({"mmg": -100, "firetext": 50}, {"mmg": 0, "firetext": 60}),
        ({"mmg": 50, "firetext": -100}, {"mmg": 40, "firetext": -90}),
    ],
)
def test_reduce_sms_provider_priority_adjusts_provider_priorities(
    mocker,
    restore_provider_details,
    notify_user,
    starting_priorities,
    expected_priorities,
):
    mock_adjust = mocker.patch("app.dao.provider_details_dao._adjust_provider_priority")

    mmg = get_provider_details_by_identifier("mmg")
    firetext = get_provider_details_by_identifier("firetext")

    mmg.priority = starting_priorities["mmg"]
    firetext.priority = starting_priorities["firetext"]
    # need to update these manually to avoid triggering the `onupdate` clause of the updated_at column
    ProviderDetails.query.filter(ProviderDetails.notification_type == "sms").update({"updated_at": datetime.min})

    # switch away from mmg. currently both 50/50
    dao_reduce_sms_provider_priority("mmg", time_threshold=timedelta(minutes=10))

    mock_adjust.assert_any_call(firetext, expected_priorities["firetext"])
    mock_adjust.assert_any_call(mmg, expected_priorities["mmg"])


def test_reduce_sms_provider_priority_does_nothing_if_providers_have_recently_changed(
    mocker,
    restore_provider_details,
):
    mock_get_providers = mocker.patch("app.dao.provider_details_dao._get_sms_providers_for_update", return_value=[])
    mock_adjust = mocker.patch("app.dao.provider_details_dao._adjust_provider_priority")

    dao_reduce_sms_provider_priority("firetext", time_threshold=timedelta(minutes=5))

    mock_get_providers.assert_called_once_with(timedelta(minutes=5))
    assert mock_adjust.called is False


def test_reduce_sms_provider_priority_does_nothing_if_there_is_only_one_active_provider(
    mocker,
    restore_provider_details,
):
    firetext = get_provider_details_by_identifier("firetext")
    firetext.active = False

    mock_adjust = mocker.patch("app.dao.provider_details_dao._adjust_provider_priority")

    dao_reduce_sms_provider_priority("firetext", time_threshold=timedelta(minutes=5))

    assert mock_adjust.called is False


@pytest.mark.parametrize(
    "existing_mmg, existing_firetext, new_mmg, new_firetext",
    [
        (50, 50, 60, 40),  # not just 50/50 - 60/40 specifically
        (65, 35, 60, 40),  # doesn't overshoot if there's less than 10 difference
        (0, 100, 10, 90),  # only adjusts by 10
        (100, 100, 90, 90),  # it tries to fix weird data - it will reduce both if needs be
    ],
)
def test_adjust_provider_priority_back_to_resting_points_updates_all_providers(
    restore_provider_details, mocker, existing_mmg, existing_firetext, new_mmg, new_firetext
):
    mmg = get_provider_details_by_identifier("mmg")
    firetext = get_provider_details_by_identifier("firetext")
    mmg.priority = existing_mmg
    firetext.priority = existing_firetext

    mock_adjust = mocker.patch("app.dao.provider_details_dao._adjust_provider_priority")
    mock_get_providers = mocker.patch(
        "app.dao.provider_details_dao._get_sms_providers_for_update", return_value=[mmg, firetext]
    )

    dao_adjust_provider_priority_back_to_resting_points()

    mock_get_providers.assert_called_once_with(timedelta(minutes=15))
    mock_adjust.assert_any_call(mmg, new_mmg)
    mock_adjust.assert_any_call(firetext, new_firetext)


def test_adjust_provider_priority_back_to_resting_points_does_nothing_if_theyre_already_at_right_values(
    restore_provider_details,
    mocker,
):
    mmg = get_provider_details_by_identifier("mmg")
    firetext = get_provider_details_by_identifier("firetext")
    mmg.priority = 60
    firetext.priority = 40

    mock_adjust = mocker.patch("app.dao.provider_details_dao._adjust_provider_priority")
    mocker.patch("app.dao.provider_details_dao._get_sms_providers_for_update", return_value=[mmg, firetext])

    dao_adjust_provider_priority_back_to_resting_points()

    assert mock_adjust.called is False


def test_adjust_provider_priority_back_to_resting_points_does_nothing_if_no_providers_to_update(
    restore_provider_details,
    mocker,
):
    mock_adjust = mocker.patch("app.dao.provider_details_dao._adjust_provider_priority")
    mocker.patch("app.dao.provider_details_dao._get_sms_providers_for_update", return_value=[])

    dao_adjust_provider_priority_back_to_resting_points()

    assert mock_adjust.called is False


@freeze_time("2018-06-28 12:00")
def test_dao_get_provider_stats(notify_db_session):
    service_1 = create_service(service_name="1")
    service_2 = create_service(service_name="2")
    sms_template_1 = create_template(service_1, "sms")
    sms_template_2 = create_template(service_2, "sms")

    create_ft_billing("2017-06-05", sms_template_2, provider="firetext", billable_unit=4)
    create_ft_billing("2018-05-31", sms_template_1, provider="mmg", billable_unit=1)
    create_ft_billing("2018-06-01", sms_template_1, provider="mmg", rate_multiplier=2, billable_unit=1)
    create_ft_billing("2018-06-03", sms_template_2, provider="firetext", billable_unit=4)
    create_ft_billing("2018-06-15", sms_template_1, provider="firetext", billable_unit=1)
    create_ft_billing("2018-06-28", sms_template_2, provider="mmg", billable_unit=2)

    results = dao_get_provider_stats()

    assert len(results) > 0

    ses = next(result for result in results if result.identifier == "ses")
    firetext = next(result for result in results if result.identifier == "firetext")
    mmg = next(result for result in results if result.identifier == "mmg")

    assert ses.display_name == "AWS SES"
    assert ses.created_by_name is None
    assert ses.current_month_billable_sms == 0

    assert firetext.display_name == "Firetext"
    assert firetext.notification_type == "sms"
    assert firetext.supports_international is False
    assert firetext.active is True
    assert firetext.current_month_billable_sms == 5

    assert mmg.identifier == "mmg"
    assert mmg.display_name == "MMG"
    assert mmg.supports_international is True
    assert mmg.active is True
    assert mmg.current_month_billable_sms == 4
