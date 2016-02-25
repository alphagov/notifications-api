from app.csv import get_recipient_from_csv
from tests.app import load_example_csv


def test_should_process_single_phone_number_file():
    sms_file = load_example_csv('sms')
    len(get_recipient_from_csv(sms_file)) == 1
    assert get_recipient_from_csv(sms_file)[0] == '+441234123123'


def test_should_process_multple_phone_number_file_in_order():
    sms_file = load_example_csv('multiple_sms')
    len(get_recipient_from_csv(sms_file)) == 10
    assert get_recipient_from_csv(sms_file)[0] == '+441234123121'
    assert get_recipient_from_csv(sms_file)[9] == '+441234123120'


def test_should_process_single_email_file():
    sms_file = load_example_csv('email')
    len(get_recipient_from_csv(sms_file)) == 1
    assert get_recipient_from_csv(sms_file)[0] == 'test@test.com'


def test_should_process_multple_email_file_in_order():
    sms_file = load_example_csv('multiple_email')
    len(get_recipient_from_csv(sms_file)) == 10
    assert get_recipient_from_csv(sms_file)[0] == 'test1@test.com'
    assert get_recipient_from_csv(sms_file)[9] == 'test0@test.com'
