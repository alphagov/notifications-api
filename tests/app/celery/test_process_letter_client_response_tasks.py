from app.celery.process_letter_client_response_tasks import check_billable_units_by_id, process_letter_callback_data


def test_check_billable_units_by_id_logs_error_if_billable_units_do_not_match_page_count(
    sample_letter_notification,
    caplog,
):
    check_billable_units_by_id(sample_letter_notification, 5)

    assert (
        f"Notification with id {sample_letter_notification.id} has 1 billable_units but DVLA says page count is 5"
    ) in caplog.messages


def test_process_letter_callback_data_checks_billable_units(mocker, sample_letter_notification):
    mock_check_billable_units = mocker.patch(
        "app.celery.process_letter_client_response_tasks.check_billable_units_by_id"
    )

    process_letter_callback_data(sample_letter_notification.id, 5)

    mock_check_billable_units.assert_called_once_with(sample_letter_notification, 5)
