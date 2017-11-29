from datetime import datetime

import pytest
from freezegun import freeze_time

from app.models import ServiceInboundApi, Service
from tests.app.db import (
    create_inbound_sms, create_service, create_service_with_inbound_number,
    create_service_inbound_api
)


def test_post_to_get_inbound_sms_with_no_params(admin_request, sample_service):
    one = create_inbound_sms(sample_service)
    two = create_inbound_sms(sample_service)

    sms = admin_request.post(
        'inbound_sms.post_query_inbound_sms_for_service',
        service_id=sample_service.id,
        _data={}
    )['data']

    assert len(sms) == 2
    assert {inbound['id'] for inbound in sms} == {str(one.id), str(two.id)}
    assert sms[0]['content'] == 'Hello'
    assert set(sms[0].keys()) == {
        'id',
        'created_at',
        'service_id',
        'notify_number',
        'user_number',
        'content'
    }


def test_post_to_get_inbound_sms_with_limit(admin_request, sample_service):
    with freeze_time('2017-01-01'):
        one = create_inbound_sms(sample_service)
    with freeze_time('2017-01-02'):
        two = create_inbound_sms(sample_service)

    data = {'limit': 1}

    sms = admin_request.post(
        'inbound_sms.post_query_inbound_sms_for_service',
        service_id=sample_service.id,
        _data=data
    )['data']

    assert len(sms) == 1
    assert sms[0]['id'] == str(two.id)


def test_post_to_get_inbound_sms_should_error_with_invalid_limit(admin_request, sample_service):
    data = {'limit': 'limit'}

    error_resp = admin_request.post(
        'inbound_sms.post_query_inbound_sms_for_service',
        service_id=sample_service.id,
        _data=data,
        _expected_status=400
    )

    assert error_resp['status_code'] == 400
    assert error_resp['errors'] == [{
        'error': 'ValidationError',
        'message': "limit limit is not of type integer, null"
    }]


@pytest.mark.parametrize('user_number', [
    '(07700) 900-001',
    '+4407700900001',
    '447700900001',
])
def test_post_to_get_inbound_sms_filters_user_number(admin_request, sample_service, user_number):
    # user_number in the db is international and normalised
    one = create_inbound_sms(sample_service, user_number='447700900001')
    two = create_inbound_sms(sample_service, user_number='447700900002')

    data = {
        'limit': 1,
        'phone_number': user_number
    }

    sms = admin_request.post(
        'inbound_sms.post_query_inbound_sms_for_service',
        service_id=sample_service.id,
        _data=data
    )['data']

    assert len(sms) == 1
    assert sms[0]['id'] == str(one.id)
    assert sms[0]['user_number'] == str(one.user_number)


def test_post_to_get_inbound_sms_filters_international_user_number(admin_request, sample_service):
    # user_number in the db is international and normalised
    one = create_inbound_sms(sample_service, user_number='12025550104')
    two = create_inbound_sms(sample_service)

    data = {
        'limit': 1,
        'phone_number': '+1 (202) 555-0104'
    }

    sms = admin_request.post(
        'inbound_sms.post_query_inbound_sms_for_service',
        service_id=sample_service.id,
        _data=data
    )['data']

    assert len(sms) == 1
    assert sms[0]['id'] == str(one.id)
    assert sms[0]['user_number'] == str(one.user_number)


def test_post_to_get_inbound_sms_allows_badly_formatted_number(admin_request, sample_service):
    one = create_inbound_sms(sample_service, user_number='ALPHANUM3R1C')

    sms = admin_request.post(
        'inbound_sms.get_inbound_sms_for_service',
        service_id=sample_service.id,
        _data={'phone_number': 'ALPHANUM3R1C'}
    )['data']

    assert len(sms) == 1
    assert sms[0]['id'] == str(one.id)
    assert sms[0]['user_number'] == str(one.user_number)


##############################################################
# REMOVE ONCE ADMIN MIGRATED AND GET ENDPOINT REMOVED
##############################################################


def test_old_get_inbound_sms(admin_request, sample_service):
    one = create_inbound_sms(sample_service)
    two = create_inbound_sms(sample_service)

    json_resp = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        service_id=sample_service.id
    )

    sms = json_resp['data']

    assert len(sms) == 2
    assert {inbound['id'] for inbound in sms} == {str(one.id), str(two.id)}
    assert sms[0]['content'] == 'Hello'
    assert set(sms[0].keys()) == {
        'id',
        'created_at',
        'service_id',
        'notify_number',
        'user_number',
        'content'
    }


def test_old_get_inbound_sms_limits(admin_request, sample_service):
    with freeze_time('2017-01-01'):
        one = create_inbound_sms(sample_service)
    with freeze_time('2017-01-02'):
        two = create_inbound_sms(sample_service)

    sms = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        service_id=sample_service.id,
        limit=1,
    )

    assert len(sms['data']) == 1
    assert sms['data'][0]['id'] == str(two.id)


@pytest.mark.parametrize('user_number', [
    '(07700) 900-001',
    '+4407700900001',
    '447700900001',
])
def test_old_get_inbound_sms_filters_user_number(admin_request, sample_service, user_number):
    # user_number in the db is international and normalised
    one = create_inbound_sms(sample_service, user_number='447700900001')
    two = create_inbound_sms(sample_service, user_number='447700900002')

    sms = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        service_id=sample_service.id,
        user_number=user_number,
    )

    assert len(sms['data']) == 1
    assert sms['data'][0]['id'] == str(one.id)
    assert sms['data'][0]['user_number'] == str(one.user_number)


def test_old_get_inbound_sms_filters_international_user_number(admin_request, sample_service):
    # user_number in the db is international and normalised
    one = create_inbound_sms(sample_service, user_number='12025550104')
    two = create_inbound_sms(sample_service)

    sms = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        service_id=sample_service.id,
        user_number='+1 (202) 555-0104',
    )

    assert len(sms['data']) == 1
    assert sms['data'][0]['id'] == str(one.id)
    assert sms['data'][0]['user_number'] == str(one.user_number)


def test_old_get_inbound_sms_allows_badly_formatted_number(admin_request, sample_service):
    one = create_inbound_sms(sample_service, user_number='ALPHANUM3R1C')

    sms = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        service_id=sample_service.id,
        user_number='ALPHANUM3R1C',
    )

    assert len(sms['data']) == 1
    assert sms['data'][0]['id'] == str(one.id)
    assert sms['data'][0]['user_number'] == str(one.user_number)


##############################
# End delete section
##############################

def test_get_inbound_sms_summary(admin_request, sample_service):
    other_service = create_service(service_name='other_service')
    with freeze_time('2017-01-01'):
        create_inbound_sms(sample_service)
    with freeze_time('2017-01-02'):
        create_inbound_sms(sample_service)
    with freeze_time('2017-01-03'):
        create_inbound_sms(other_service)

    summary = admin_request.get(
        'inbound_sms.get_inbound_sms_summary_for_service',
        service_id=sample_service.id
    )

    assert summary == {
        'count': 2,
        'most_recent': datetime(2017, 1, 2).isoformat()
    }


def test_get_inbound_sms_summary_with_no_inbound(admin_request, sample_service):
    summary = admin_request.get(
        'inbound_sms.get_inbound_sms_summary_for_service',
        service_id=sample_service.id
    )

    assert summary == {
        'count': 0,
        'most_recent': None
    }


def test_get_inbound_sms_by_id_returns_200(admin_request, notify_db_session):
    service = create_service_with_inbound_number(inbound_number='12345')
    inbound = create_inbound_sms(service=service, user_number='447700900001')

    response = admin_request.get(
        'inbound_sms.get_inbound_by_id',
        service_id=service.id,
        inbound_sms_id=inbound.id,
    )

    assert response['user_number'] == '447700900001'
    assert response['service_id'] == str(service.id)


def test_get_inbound_sms_by_id_invalid_id_returns_404(admin_request, sample_service):
    assert admin_request.get(
        'inbound_sms.get_inbound_by_id',
        service_id=sample_service.id,
        inbound_sms_id='bar',
        _expected_status=404
    )


def test_get_inbound_sms_by_id_with_invalid_service_id_returns_404(admin_request, sample_service):
    assert admin_request.get(
        'inbound_sms.get_inbound_by_id',
        service_id='foo',
        inbound_sms_id='2cfbd6a1-1575-4664-8969-f27be0ea40d9',
        _expected_status=404
    )


def test_inbound_api_blah(notify_db_session):
    service = create_service()
    api = create_service_inbound_api(service=service)

    print("***************")
    from_db = Service.query.all()[0]
    print("--------------------")
    from_db_service = from_db.inbound_api
    print("***************")
    assert 1 == 1
