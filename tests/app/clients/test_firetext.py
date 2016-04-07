import pytest

from app.clients.sms.firetext import get_firetext_responses


def test_should_return_correct_details_for_delivery():
    response_dict = get_firetext_responses('0')
    assert response_dict['message'] == 'Delivered'
    assert response_dict['notification_status'] == 'delivered'
    assert response_dict['notification_statistics_status'] == 'delivered'
    assert response_dict['success']


def test_should_return_correct_details_for_bounced():
    response_dict = get_firetext_responses('1')
    assert response_dict['message'] == 'Declined'
    assert response_dict['notification_status'] == 'failed'
    assert response_dict['notification_statistics_status'] == 'failure'
    assert not response_dict['success']


def test_should_return_correct_details_for_complaint():
    response_dict = get_firetext_responses('2')
    assert response_dict['message'] == 'Undelivered (Pending with Network)'
    assert response_dict['notification_status'] == 'sent'
    assert not response_dict['notification_statistics_status']
    assert not response_dict['success']


def test_should_be_none_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        get_firetext_responses('99')
    assert '99' in str(e.value)
