def test_unsubscribe_request_returns_correct_number_of_pending_requests(admin_request, sample_email_notification):
    pending_unsubscribe_requests = 250
    response = admin_request.get("unsubscribe_requests.unsubscribe_requests_summary", notification_id=sample_email_notification.id)
    assert response["pending_unsubscribe_requests"] == pending_unsubscribe_requests