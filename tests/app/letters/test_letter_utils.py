import pytest

from freezegun import freeze_time

from app.letters.utils import get_bucket_prefix_for_notification, get_letter_pdf_filename


def test_get_bucket_prefix_for_notification_valid_notification(sample_notification):

    bucket_prefix = get_bucket_prefix_for_notification(sample_notification)

    assert bucket_prefix == '{folder}/NOTIFY.{reference}'.format(
        folder=sample_notification.created_at.date(),
        reference=sample_notification.reference
    ).upper()


def test_get_bucket_prefix_for_notification_invalid_notification():
    with pytest.raises(AttributeError):
        get_bucket_prefix_for_notification(None)


@pytest.mark.parametrize('crown_flag,expected_crown_text', [
    (True, 'C'),
    (False, 'N'),
])
@freeze_time("2017-12-04 17:29:00")
def test_get_letter_pdf_filename_returns_correct_filename(
        notify_api, mocker, crown_flag, expected_crown_text):
    filename = get_letter_pdf_filename(reference='foo', crown=crown_flag)

    assert filename == '2017-12-04/NOTIFY.FOO.D.2.C.{}.20171204172900.PDF'.format(expected_crown_text)


@freeze_time("2017-12-04 17:29:00")
def test_get_letter_pdf_filename_returns_correct_filename_for_test_letters(
        notify_api, mocker):
    filename = get_letter_pdf_filename(reference='foo', crown='C', is_test_letter=True)

    assert filename == 'NOTIFY.FOO.D.2.C.C.20171204172900.PDF'


@freeze_time("2017-12-04 17:31:00")
def test_get_letter_pdf_filename_returns_tomorrows_filename(notify_api, mocker):
    filename = get_letter_pdf_filename(reference='foo', crown=True)

    assert filename == '2017-12-05/NOTIFY.FOO.D.2.C.C.20171204173100.PDF'
