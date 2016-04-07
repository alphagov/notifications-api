import json
from freezegun import freeze_time

from app import db
from app.models import TemplateStatistics

from tests import create_authorization_header


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

            auth_header = create_authorization_header(
                path='/service/{}/template-statistics'.format(sample_template.service_id),
                method='GET'
            )

            response = client.get(
                '/service/{}/template-statistics'.format(sample_template.service_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                query_string={'limit_days': 7}
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 7
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

            auth_header = create_authorization_header(
                path='/service/{}/template-statistics'.format(sample_template.service_id),
                method='GET'
            )

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

            auth_header = create_authorization_header(
                path='/service/{}/template-statistics'.format(sample_template.service_id),
                method='GET'
            )

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

            auth_header = create_authorization_header(
                path='/service/{}/template-statistics'.format(sample_template.service_id),
                method='GET'
            )

            response = client.get(
                '/service/{}/template-statistics'.format(sample_template.service_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                query_string={'limit_days': 'blurk'}
            )

            assert response.status_code == 400
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == {'limit_days': ['blurk is not an integer']}
