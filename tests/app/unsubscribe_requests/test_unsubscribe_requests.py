
def unsubscribe_summary_url_get(admin_request, notification_id):
    return admin_request.get(f"/unsubscribe/{notification_id}/summary")

def test_unsubscribe_request_returns_correct_number_of_pending_requests(client, sample_email_notification):
    pending_unsubscribe_requests = 250
    response = unsubscribe_summary_url_get(client, 12345)
    response_json_data = response.get_json()
    assert response.status_code == 200
    assert response_json_data["pending_unsubscribe_requests"] == pending_unsubscribe_requests