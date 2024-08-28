import pytest

from app.models import Notification
from app.service.send_notification import send_one_off_notification


@pytest.mark.parametrize(
    "last_line_of_address, expected_postage, expected_international",
    [("France", "europe", True), ("Canada", "rest-of-world", True), ("SW1 1AA", "second", False)],
)
def test_send_notification_should_send_international_letters(
    sample_letter_template, mocker, last_line_of_address, expected_postage, expected_international
):
    deliver_mock = mocker.patch("app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async")
    data = {
        "template_id": sample_letter_template.id,
        "personalisation": {
            "address_line_1": "Jane",
            "address_line_2": "Rue Vert",
            "address_line_3": last_line_of_address,
        },
        "to": "Jane",
        "created_by": sample_letter_template.service.created_by_id,
    }

    notification_id = send_one_off_notification(sample_letter_template.service_id, data)
    assert deliver_mock.called
    notification = Notification.query.get(notification_id["id"])
    assert notification.postage == expected_postage
    assert notification.international == expected_international


@pytest.mark.parametrize("reference_paceholder,", [None, "ref2"])
def test_send_notification_should_set_client_reference_from_placeholder(
    sample_letter_template, mocker, reference_paceholder
):
    deliver_mock = mocker.patch("app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async")
    data = {
        "template_id": sample_letter_template.id,
        "personalisation": {
            "address_line_1": "Jane",
            "address_line_2": "Moss Lane",
            "address_line_3": "SW1A 1AA",
        },
        "to": "Jane",
        "created_by": sample_letter_template.service.created_by_id,
    }
    if reference_paceholder:
        data["personalisation"]["reference"] = reference_paceholder

    notification_id = send_one_off_notification(sample_letter_template.service_id, data)
    assert deliver_mock.called
    notification = Notification.query.get(notification_id["id"])
    assert notification.client_reference == reference_paceholder
