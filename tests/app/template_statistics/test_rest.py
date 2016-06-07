from datetime import datetime
import json

from freezegun import freeze_time

from app import db
from app.models import TemplateStatistics
from tests import create_authorization_header
from tests.app.conftest import sample_template as create_sample_template


@freeze_time('2016-04-09')
def test_get_template_statistics_for_service_for_last_week(notify_api, sample_template):

    # make 9 stats records from 1st to 9th April
    for i in range(1, 10):
        past_date = '2016-04-0{}'.format(i)
        with freeze_time(past_date):
            template_stats = TemplateStatistics(template_id=sample_template.id,
                                                service_id=sample_template.service_id)
            db.session.add(template_stats)
            db.session.commit()

    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/template-statistics'.format(sample_template.service_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                query_string={'limit_days': 7}
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 8
            assert json_resp['data'][0]['day'] == '2016-04-09'
            assert json_resp['data'][6]['day'] == '2016-04-03'


@freeze_time('2016-04-30')
def test_get_template_statistics_for_service_for_last_week_with_no_data(notify_api, sample_template):

    # make 9 stats records from 1st to 9th April
    for i in range(1, 10):
        past_date = '2016-04-0{}'.format(i)
        with freeze_time(past_date):
            template_stats = TemplateStatistics(template_id=sample_template.id,
                                                service_id=sample_template.service_id)
            db.session.add(template_stats)
            db.session.commit()

    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header()

            # Date is frozen at 2016-04-30 and no data written since
            response = client.get(
                '/service/{}/template-statistics'.format(sample_template.service_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                query_string={'limit_days': 7}
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 0

            response = client.get(
                '/service/{}/template-statistics'.format(sample_template.service_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                query_string={'limit_days': 30}
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 9


def test_get_all_template_statistics_for_service(notify_api, sample_template):

    # make 9 stats records from 1st to 9th April
    for i in range(1, 10):
        past_date = '2016-04-0{}'.format(i)
        with freeze_time(past_date):
            template_stats = TemplateStatistics(template_id=sample_template.id,
                                                service_id=sample_template.service_id)
            db.session.add(template_stats)
            db.session.commit()

    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/template-statistics'.format(sample_template.service_id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 9
            assert json_resp['data'][0]['day'] == '2016-04-09'
            assert json_resp['data'][8]['day'] == '2016-04-01'


def test_get_all_template_statistics_with_bad_limit_arg_returns_400(notify_api, sample_template):

    # make 9 stats records from 1st to 9th April
    for i in range(1, 10):
        past_date = '2016-04-0{}'.format(i)
        with freeze_time(past_date):
            template_stats = TemplateStatistics(template_id=sample_template.id,
                                                service_id=sample_template.service_id)
            db.session.add(template_stats)
            db.session.commit()

    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/template-statistics'.format(sample_template.service_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                query_string={'limit_days': 'blurk'}
            )

            assert response.status_code == 400
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == {'limit_days': ['blurk is not an integer']}


def test_get_template_statistics_for_template_only_returns_for_provided_template(
        notify_db,
        notify_db_session,
        notify_api,
        sample_service
):
    template_1 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 1',
        service=sample_service
    )
    template_2 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 2',
        service=sample_service
    )

    template_1_stats_1 = TemplateStatistics(
        template_id=template_1.id,
        service_id=sample_service.id,
        day=datetime(2001, 1, 1)
    )
    template_1_stats_2 = TemplateStatistics(
        template_id=template_1.id,
        service_id=sample_service.id,
        day=datetime(2001, 1, 2)
    )
    template_2_stats = TemplateStatistics(
        template_id=template_2.id,
        service_id=sample_service.id,
        day=datetime(2001, 1, 1)
    )
    db.session.add_all([template_1_stats_1, template_1_stats_2, template_2_stats])
    db.session.commit()

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/template-statistics/{}'.format(sample_service.id, template_1.id),
                headers=[('Content-Type', 'application/json'), auth_header],
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 2
            assert json_resp['data'][0]['id'] == str(template_1_stats_1.id)
            assert json_resp['data'][1]['id'] == str(template_1_stats_2.id)


def test_get_template_statistics_for_template_returns_empty_if_no_statistics(
        notify_db,
        notify_db_session,
        notify_api,
        sample_service
):
    template_1 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 1',
        service=sample_service
    )
    template_2 = create_sample_template(
        notify_db,
        notify_db_session,
        template_name='Sample Template 2',
        service=sample_service
    )

    template_1_stats = TemplateStatistics(
        template_id=template_1.id,
        service_id=sample_service.id,
        day=datetime(2001, 1, 1)
    )
    db.session.add(template_1_stats)
    db.session.commit()

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/template-statistics/{}'.format(sample_service.id, template_2.id),
                headers=[('Content-Type', 'application/json'), auth_header],
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['data'] == []
