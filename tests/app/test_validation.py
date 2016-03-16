from app.models import User, Service
from app.validation import allowed_send_to_number, allowed_send_to_email


def test_allowed_send_to_number_returns_true_for_restricted_service_with_same_number():
    mobile_number = '07524609792'
    service = _create_service_data(mobile_number)
    assert allowed_send_to_number(service, mobile_number)


def test_allowed_send_to_number_returns_false_for_restricted_service_with_different_number():
    mobile_number = '00447524609792'
    service = _create_service_data(mobile_number)
    assert not allowed_send_to_number(service, '+447344609793')


def test_allowed_send_to_number_returns_true_for_unrestricted_service_with_different_number():
    mobile_number = '+447524609792'
    service = _create_service_data(mobile_number, False)
    assert allowed_send_to_number(service, '+447344609793')


def test_allowed_send_to_email__returns_true_for_restricted_service_with_same_email():
    email = 'testing@it.gov.uk'
    service = _create_service_data(email_address=email)
    assert allowed_send_to_email(service, email)


def test_allowed_send_to_email__returns_false_for_restricted_service_with_different_email():
    email = 'testing@it.gov.uk'
    service = _create_service_data(email_address=email)
    assert not allowed_send_to_email(service, 'another@it.gov.uk')


def test_allowed_send_to_email__returns_false_for_restricted_service_with_different_email():
    email = 'testing@it.gov.uk'
    service = _create_service_data(email_address=email)
    assert not allowed_send_to_email(service, 'another@it.gov.uk')


def test_allowed_send_to_email__returns_true_for_unrestricted_service_with_different_email():
    email = 'testing@it.gov.uk'
    service = _create_service_data(email_address=email, restricted=False)
    assert allowed_send_to_number(service, 'another@it.gov.uk')


def _create_service_data(mobile_number='+447524609792', restricted=True, email_address='test_user@it.gov.uk'):
    usr = {
        'name': 'Test User',
        'email_address': email_address,
        'password': 'password',
        'mobile_number': mobile_number,
        'state': 'active'
    }
    user = User(**usr)
    data = {
        'name': 'Test service',
        'limit': 10,
        'active': False,
        'restricted': restricted,
        'email_from': 'test_service@it.gov.uk'
    }
    service = Service(**data)
    service.users = [user]
    return service
