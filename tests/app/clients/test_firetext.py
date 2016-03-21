import pytest

from app.clients.sms import firetext

responses = firetext.FiretextResponses()


def test_should_return_correct_details_for_delivery():
    assert responses.response_code_to_message('0') == 'Delivered'
    assert responses.response_code_to_notification_status('0') == 'delivered'
    assert responses.response_code_to_notification_statistics_status('0') == 'delivered'
    assert responses.response_code_to_notification_success('0')


def test_should_return_correct_details_for_bounced():
    assert responses.response_code_to_message('1') == 'Declined'
    assert responses.response_code_to_notification_status('1') == 'failed'
    assert responses.response_code_to_notification_statistics_status('1') == 'failure'
    assert not responses.response_code_to_notification_success('1')


def test_should_return_correct_details_for_complaint():
    assert responses.response_code_to_message('2') == 'Undelivered (Pending with Network)'
    assert responses.response_code_to_notification_status('2') == 'sent'
    assert not responses.response_code_to_notification_statistics_status('2')
    assert not responses.response_code_to_notification_success('2')


def test_should_be_none_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        responses.response_code_to_object('99')
    assert '99' in str(e.value)
