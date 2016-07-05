import pytest
from unittest.mock import Mock, ANY

from app import aws_ses_client
from app.clients.email.aws_ses import get_aws_responses


def test_should_return_correct_details_for_delivery():
    response_dict = get_aws_responses('Delivery')
    assert response_dict['message'] == 'Delivered'
    assert response_dict['notification_status'] == 'delivered'
    assert response_dict['notification_statistics_status'] == 'delivered'
    assert response_dict['success']


def test_should_return_correct_details_for_hard_bounced():
    response_dict = get_aws_responses('Permanent')
    assert response_dict['message'] == 'Hard bounced'
    assert response_dict['notification_status'] == 'permanent-failure'
    assert response_dict['notification_statistics_status'] == 'failure'
    assert not response_dict['success']


def test_should_return_correct_details_for_soft_bounced():
    response_dict = get_aws_responses('Temporary')
    assert response_dict['message'] == 'Soft bounced'
    assert response_dict['notification_status'] == 'temporary-failure'
    assert response_dict['notification_statistics_status'] == 'failure'
    assert not response_dict['success']


def test_should_return_correct_details_for_complaint():
    response_dict = get_aws_responses('Complaint')
    assert response_dict['message'] == 'Complaint'
    assert response_dict['notification_status'] == 'delivered'
    assert response_dict['notification_statistics_status'] == 'delivered'
    assert response_dict['success']


def test_should_be_none_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        get_aws_responses('99')
    assert '99' in str(e.value)


@pytest.mark.parametrize(
    'reply_to_address, expected_value',
    [(None, []), ('foo@bar.com', ['foo@bar.com'])],
    ids=['empty', 'single_email']
)
def test_send_email_handles_reply_to_address(notify_api, mocker, reply_to_address, expected_value):
    boto_mock = mocker.patch.object(aws_ses_client, '_client', create=True)
    mocker.patch.object(aws_ses_client, 'statsd_client', create=True)

    with notify_api.app_context():
        aws_ses_client.send_email(
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            reply_to_address=reply_to_address
        )

    boto_mock.send_email.assert_called_once_with(
        Source=ANY,
        Destination=ANY,
        Message=ANY,
        ReplyToAddresses=expected_value
    )
