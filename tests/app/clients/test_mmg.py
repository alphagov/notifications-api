from app.clients.sms.mmg import get_mmg_responses


def test_should_return_correct_details_for_delivery():
    response_dict = get_mmg_responses('0')
    assert response_dict['message'] == 'Delivered'
    assert response_dict['notification_status'] == 'delivered'
    assert response_dict['notification_statistics_status'] == 'delivered'
    assert response_dict['success']


def test_should_return_correct_details_for_bounced():
    response_dict = get_mmg_responses('50')
    assert response_dict['message'] == 'Declined'
    assert response_dict['notification_status'] == 'failed'
    assert response_dict['notification_statistics_status'] == 'failure'
    assert not response_dict['success']


def test_should_be_none_if_unrecognised_status_code():
    response_dict = get_mmg_responses('blah')
    assert response_dict['message'] == 'Declined'
    assert response_dict['notification_status'] == 'failed'
    assert response_dict['notification_statistics_status'] == 'failure'
    assert not response_dict['success']
