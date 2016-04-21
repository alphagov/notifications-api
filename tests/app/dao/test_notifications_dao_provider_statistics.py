from datetime import datetime
from app.models import ProviderStatistics

from app.dao.provider_statistics_dao import get_provider_statistics
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
    provider_stats = get_provider_statistics(sample_template.service, mmg_provider_name)
    assert provider_stats.unit_count == 1


def test_should_update_provider_statistics_email(notify_db,
                                                 notify_db_session,
                                                 sample_email_template,
                                                 ses_provider_name):
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    provider_stats = get_provider_statistics(sample_email_template.service, ses_provider_name)
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
    provider_stats = get_provider_statistics(sample_template.service, mmg_provider_name)
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
    provider_stats = get_provider_statistics(sample_email_template.service, ses_provider_name)
    assert provider_stats.unit_count == 3
