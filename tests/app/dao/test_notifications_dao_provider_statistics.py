from datetime import (date, timedelta)
from app.models import ProviderStatistics
from app.dao.notifications_dao import update_provider_stats
from app.dao.provider_statistics_dao import (
    get_provider_statistics, get_fragment_count)
from tests.app.conftest import sample_notification as create_sample_notification


def test_should_update_provider_statistics_sms(notify_db,
                                               notify_db_session,
                                               sample_template,
                                               mmg_provider):
    n1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        dao_create=True)
    update_provider_stats(n1.id, 'sms', mmg_provider.identifier)
    provider_stats = get_provider_statistics(
        sample_template.service,
        providers=[mmg_provider.identifier]).one()
    assert provider_stats.unit_count == 1


def test_should_update_provider_statistics_email(notify_db,
                                                 notify_db_session,
                                                 sample_email_template,
                                                 ses_provider):
    n1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        dao_create=True)
    update_provider_stats(n1.id, 'email', ses_provider.identifier)
    provider_stats = get_provider_statistics(
        sample_email_template.service,
        providers=[ses_provider.identifier]).one()
    assert provider_stats.unit_count == 1


def test_should_update_provider_statistics_sms_multi(notify_db,
                                                     notify_db_session,
                                                     sample_template,
                                                     mmg_provider):
    n1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        provider_name=mmg_provider.identifier,
        content_char_count=160,
        dao_create=True)
    update_provider_stats(n1.id, 'sms', mmg_provider.identifier)
    n2 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        provider_name=mmg_provider.identifier,
        content_char_count=161,
        dao_create=True)
    update_provider_stats(n2.id, 'sms', mmg_provider.identifier)
    n3 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        provider_name=mmg_provider.identifier,
        content_char_count=307,
        dao_create=True)
    update_provider_stats(n3.id, 'sms', mmg_provider.identifier)
    provider_stats = get_provider_statistics(
        sample_template.service,
        providers=[mmg_provider.identifier]).one()
    assert provider_stats.unit_count == 6


def test_should_update_provider_statistics_email_multi(notify_db,
                                                       notify_db_session,
                                                       sample_email_template,
                                                       ses_provider):
    n1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        provider_name=ses_provider.identifier,
        dao_create=True)
    update_provider_stats(n1.id, 'email', ses_provider.identifier)
    n2 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        provider_name=ses_provider.identifier,
        dao_create=True)
    update_provider_stats(n2.id, 'email', ses_provider.identifier)
    n3 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        provider_name=ses_provider.identifier,
        dao_create=True)
    update_provider_stats(n3.id, 'email', ses_provider.identifier)
    provider_stats = get_provider_statistics(
        sample_email_template.service,
        providers=[ses_provider.identifier]).one()
    assert provider_stats.unit_count == 3


def test_should_aggregate_fragment_count(notify_db,
                                         notify_db_session,
                                         sample_service,
                                         mmg_provider,
                                         firetext_provider,
                                         ses_provider):
    day = date.today()
    stats_mmg = ProviderStatistics(
        service=sample_service,
        day=day,
        provider_id=mmg_provider.id,
        unit_count=2
    )

    stats_firetext = ProviderStatistics(
        service=sample_service,
        day=day,
        provider_id=firetext_provider.id,
        unit_count=3
    )

    stats_ses = ProviderStatistics(
        service=sample_service,
        day=day,
        provider_id=ses_provider.id,
        unit_count=1
    )
    notify_db.session.add(stats_mmg)
    notify_db.session.add(stats_firetext)
    notify_db.session.add(stats_ses)
    notify_db.session.commit()
    results = get_fragment_count(sample_service, day, day)
    assert results['sms_count'] == 5
    assert results['email_count'] == 1


def test_should_aggregate_fragment_count_over_days(notify_db,
                                                   notify_db_session,
                                                   sample_service,
                                                   mmg_provider):
    today = date.today()
    yesterday = today - timedelta(days=1)
    stats_today = ProviderStatistics(
        service=sample_service,
        day=today,
        provider_id=mmg_provider.id,
        unit_count=2
    )
    stats_yesterday = ProviderStatistics(
        service=sample_service,
        day=yesterday,
        provider_id=mmg_provider.id,
        unit_count=3
    )
    notify_db.session.add(stats_today)
    notify_db.session.add(stats_yesterday)
    notify_db.session.commit()
    results = get_fragment_count(sample_service, yesterday, today)
    assert results['sms_count'] == 5
    assert results['email_count'] == 0
