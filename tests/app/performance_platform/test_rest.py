from datetime import date, datetime

from app.dao import fact_processing_time_dao
from app.models import FactProcessingTime
from tests.app.db import create_template, create_ft_notification_status


def test_performance_platform(sample_service, admin_request):
    template_sms = create_template(service=sample_service, template_type='sms', template_name='a')
    template_email = create_template(service=sample_service, template_type='email', template_name='b')
    template_letter = create_template(service=sample_service, template_type='letter', template_name='c')
    create_ft_notification_status(bst_date=date(2021, 3, 1),
                                  service=template_email.service,
                                  template=template_email,
                                  count=15)
    create_ft_notification_status(bst_date=date(2021, 3, 1),
                                  service=template_sms.service,
                                  template=template_sms,
                                  count=20)
    create_ft_notification_status(bst_date=date(2021, 3, 1),
                                  service=template_letter.service,
                                  template=template_letter,
                                  count=3)

    create_process_time()

    results = admin_request.get(endpoint="performance_platform.get_performance_platform",
                                start_date='2021-03-01',
                                end_date='2021-03-01')

    assert results['total_notifications'] == 15+20+3
    assert results['email_notifications'] == 15
    assert results['sms_notifications'] == 20
    assert results['letter_notifications'] == 3
    assert results['notifications_by_type'] == [{"date": '2021-03-01', "emails": 15, "sms": 20, "letters": 3}]
    assert results['processing_time'] == [({"date": "2021-03-01", "percentage_under_10_seconds": 97.1})]
    assert results["live_service_count"] == 1
    assert results["services_using_notify"][0]["service_name"] == sample_service.name
    assert not results["services_using_notify"][0]["organisation_name"]


def create_process_time():
    data = FactProcessingTime(
        bst_date=datetime(2021, 3, 1).date(),
        messages_total=35,
        messages_within_10_secs=34
    )
    fact_processing_time_dao.insert_update_processing_time(data)
