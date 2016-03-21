import pytest

from app.clients.email import aws_ses

aws_responses = aws_ses.AwsSesResponses()


def test_should_return_correct_details_for_delivery():
    assert aws_responses.response_code_to_message('Delivery') == 'Delivered'
    assert aws_responses.response_code_to_notification_status('Delivery') == 'delivered'
    assert aws_responses.response_code_to_notification_statistics_status('Delivery') == 'delivered'
    assert aws_responses.response_code_to_notification_success('Delivery')


def test_should_return_correct_details_for_bounced():
    assert aws_responses.response_code_to_message('Bounce') == 'Bounced'
    assert aws_responses.response_code_to_notification_status('Bounce') == 'bounce'
    assert aws_responses.response_code_to_notification_statistics_status('Bounce') == 'failed'
    assert not aws_responses.response_code_to_notification_success('Bounce')


def test_should_return_correct_details_for_complaint():
    assert aws_responses.response_code_to_message('Complaint') == 'Complaint'
    assert aws_responses.response_code_to_notification_status('Complaint') == 'complaint'
    assert aws_responses.response_code_to_notification_statistics_status('Complaint') == 'failed'
    assert not aws_responses.response_code_to_notification_success('Complaint')


def test_should_be_none_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        aws_responses.response_code_to_object('99')
    assert '99' in str(e.value)
