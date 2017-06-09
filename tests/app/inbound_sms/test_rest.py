from datetime import datetime

import pytest
from freezegun import freeze_time

from tests.app.db import create_inbound_sms, create_service


def test_get_inbound_sms(admin_request, sample_service):
    one = create_inbound_sms(sample_service)
    two = create_inbound_sms(sample_service)

    json_resp = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        endpoint_kwargs={'service_id': sample_service.id}
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
        'content',
        'provider_date',
        'provider_reference'
    }


def test_get_inbound_sms_limits(admin_request, sample_service):
    with freeze_time('2017-01-01'):
        one = create_inbound_sms(sample_service)
    with freeze_time('2017-01-02'):
        two = create_inbound_sms(sample_service)

    sms = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        endpoint_kwargs={'service_id': sample_service.id, 'limit': 1}
    )

    assert len(sms['data']) == 1
    assert sms['data'][0]['id'] == str(two.id)


@pytest.mark.parametrize('user_number', [
    '(07700) 900-001',
    '+4407700900001',
    '447700900001',
])
def test_get_inbound_sms_filters_user_number(admin_request, sample_service, user_number):
    # user_number in the db is international and normalised
    one = create_inbound_sms(sample_service, user_number='447700900001')
    two = create_inbound_sms(sample_service, user_number='447700900002')

    sms = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        endpoint_kwargs={'service_id': sample_service.id, 'user_number': user_number}
    )

    assert len(sms['data']) == 1
    assert sms['data'][0]['id'] == str(one.id)
    assert sms['data'][0]['user_number'] == str(one.user_number)


def test_get_inbound_sms_filters_international_user_number(admin_request, sample_service):
    # user_number in the db is international and normalised
    one = create_inbound_sms(sample_service, user_number='12025550104')
    two = create_inbound_sms(sample_service)

    sms = admin_request.get(
        'inbound_sms.get_inbound_sms_for_service',
        endpoint_kwargs={'service_id': sample_service.id, 'user_number': '+1 (202) 555-0104'}
    )

    assert len(sms['data']) == 1
    assert sms['data'][0]['id'] == str(one.id)
    assert sms['data'][0]['user_number'] == str(one.user_number)


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
        endpoint_kwargs={'service_id': sample_service.id}
    )

    assert summary == {
        'count': 2,
        'most_recent': datetime(2017, 1, 2).isoformat()
    }


def test_get_inbound_sms_summary_with_no_inbound(admin_request, sample_service):
    summary = admin_request.get(
        'inbound_sms.get_inbound_sms_summary_for_service',
        endpoint_kwargs={'service_id': sample_service.id}
    )

    assert summary == {
        'count': 0,
        'most_recent': None
    }


def test_get_inbound_sms_by_id_returns_200(admin_request, sample_service):
    inbound = create_inbound_sms(sample_service, user_number='447700900001')

    response = admin_request.get(
        'inbound_sms.get_inbound_by_id',
        endpoint_kwargs={
            'service_id': sample_service.id,
            'inbound_sms_id': inbound.id
        }
    )

    assert response['user_number'] == '447700900001'
    assert response['service_id'] == str(sample_service.id)


def test_get_inbound_sms_by_id_invalid_id_returns_404(admin_request, sample_service):
    assert admin_request.get(
        'inbound_sms.get_inbound_by_id',
        endpoint_kwargs={
            'service_id': sample_service.id,
            'inbound_sms_id': 'bar'
        },
        expected_status=404
    )


def test_get_inbound_sms_by_id_with_invalid_service_id_returns_404(admin_request, sample_service):
    assert admin_request.get(
        'inbound_sms.get_inbound_by_id',
        endpoint_kwargs={
            'service_id': 'foo',
            'inbound_sms_id': '2cfbd6a1-1575-4664-8969-f27be0ea40d9'
        },
        expected_status=404
    )
