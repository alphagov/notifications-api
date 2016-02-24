from app.csv import get_mobile_numbers_from_csv
from tests.app import load_example_csv


def test_should_process_single_phone_number_file():
    sms_file = load_example_csv('sms')
    len(get_mobile_numbers_from_csv(sms_file)) == 1
    assert get_mobile_numbers_from_csv(sms_file)[0] == '+441234123123'


def test_should_process_multple_phone_number_file_in_order():
    sms_file = load_example_csv('multiple_sms')
    len(get_mobile_numbers_from_csv(sms_file)) == 10
    assert get_mobile_numbers_from_csv(sms_file)[0] == '+441234123121'
    assert get_mobile_numbers_from_csv(sms_file)[9] == '+441234123120'
