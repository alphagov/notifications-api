from datetime import (date, timedelta)
from app.models import ProviderStatistics

from app.dao.provider_statistics_dao import (
    get_provider_statistics, get_fragment_count)
from app.models import Notification
from tests.app.conftest import sample_notification as create_sample_notification


def test_should_update_provider_statistics_sms(notify_db,
                                               notify_db_session,
                                               sample_template,
                                               mmg_provider_name):
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template)
    provider_stats = get_provider_statistics(
        sample_template.service,
        providers=[mmg_provider_name]).one()
    assert provider_stats.unit_count == 1


def test_should_update_provider_statistics_email(notify_db,
                                                 notify_db_session,
                                                 sample_email_template,
                                                 ses_provider_name):
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    provider_stats = get_provider_statistics(
        sample_email_template.service,
        providers=[ses_provider_name]).one()
    assert provider_stats.unit_count == 1


def test_should_update_provider_statistics_sms_multi(notify_db,
                                                     notify_db_session,
                                                     sample_template,
                                                     mmg_provider_name):
    notification1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        content_char_count=160)
    notification1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        content_char_count=161)
    notification1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        content_char_count=307)
    provider_stats = get_provider_statistics(
        sample_template.service,
        providers=[mmg_provider_name]).one()
    assert provider_stats.unit_count == 6


def test_should_update_provider_statistics_email_multi(notify_db,
                                                       notify_db_session,
                                                       sample_email_template,
                                                       ses_provider_name):
    notification1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    notification2 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    notification3 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    provider_stats = get_provider_statistics(
        sample_email_template.service,
        providers=[ses_provider_name]).one()
    assert provider_stats.unit_count == 3


def test_should_aggregate_fragment_count(notify_db,
                                         notify_db_session,
                                         sample_service,
                                         mmg_provider_name,
                                         twilio_provider_name,
                                         ses_provider_name):
    day = date.today()
    stats_mmg = ProviderStatistics(
        service=sample_service,
        day=day,
        provider=mmg_provider_name,
        unit_count=2
    )
    stats_twilio = ProviderStatistics(
        service=sample_service,
        day=day,
        provider=twilio_provider_name,
        unit_count=3
    )
    stats_twilio = ProviderStatistics(
        service=sample_service,
        day=day,
        provider=ses_provider_name,
        unit_count=1
    )
    notify_db.session.add(stats_mmg)
    notify_db.session.add(stats_twilio)
    notify_db.session.commit()
    results = get_fragment_count(sample_service, day, day)
    assert results['sms_count'] == 5
    assert results['email_count'] == 1


def test_should_aggregate_fragment_count_over_days(notify_db,
                                                   notify_db_session,
                                                   sample_service,
                                                   mmg_provider_name):
    today = date.today()
    yesterday = today - timedelta(days=1)
    stats_today = ProviderStatistics(
        service=sample_service,
        day=today,
        provider=mmg_provider_name,
        unit_count=2
    )
    stats_yesterday = ProviderStatistics(
        service=sample_service,
        day=yesterday,
        provider=mmg_provider_name,
        unit_count=3
    )
    notify_db.session.add(stats_today)
    notify_db.session.add(stats_yesterday)
    notify_db.session.commit()
    results = get_fragment_count(sample_service, yesterday, today)
    assert results['sms_count'] == 5
    assert results['email_count'] == 0
