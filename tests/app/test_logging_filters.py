import pytest
from flask import url_for

from tests import create_admin_authorization_header


@pytest.mark.usefixtures("_notify_db")
class TestUserIdFilter:
    def test_no_user_id_attribute_outside_request(self, caplog, notify_api):
        caplog.set_level("INFO")

        notify_api.logger.info("blah")
        assert caplog.records[-1].current_user_id is None

    def test_user_id_for_non_admin_requests(self, caplog, notify_api):
        caplog.set_level("INFO")

        content_type_header = ("Content-Type", "application/json")
        admin_auth_header = create_admin_authorization_header()
        user_id_header = ("x-notify-user-id", "abcdabcd-1234-1234-1234-abcdabcdabcd")

        with notify_api.test_request_context():
            with notify_api.test_client() as client:
                client.get(url_for("test.log_view"), headers=[content_type_header])
                assert caplog.records[-1].current_user_id is None

                client.get(url_for("test.log_view"), headers=[content_type_header, admin_auth_header])
                assert caplog.records[-1].current_user_id is None

                # X-Notify-User-Id provided but we're not in an admin request so it's untrusted
                client.get(url_for("test.log_view"), headers=[content_type_header, user_id_header])
                assert caplog.records[-1].current_user_id is None

                # Admin auth has been provided here, but we're not in an admin request so it's not been validated
                client.get(url_for("test.log_view"), headers=[content_type_header, admin_auth_header, user_id_header])
                assert caplog.records[-1].current_user_id is None

    def test_user_id_for_admin_requests(self, caplog, notify_api):
        caplog.set_level("INFO")

        content_type_header = ("Content-Type", "application/json")
        admin_auth_header = create_admin_authorization_header()
        user_id_header = ("x-notify-user-id", "abcdabcd-1234-1234-1234-abcdabcdabcd")

        with notify_api.test_request_context():
            with notify_api.test_client() as client:
                # No user_id - header not passed
                client.get(
                    url_for("admin_test.admin_log_view"),
                    headers=[content_type_header, admin_auth_header],
                )
                assert caplog.records[-1].current_user_id is None

                # Confirmed user ID - it's an authenticated admin view with a user id
                client.get(
                    url_for("admin_test.admin_log_view"),
                    headers=[content_type_header, admin_auth_header, user_id_header],
                )
                assert caplog.records[-1].current_user_id == "abcdabcd-1234-1234-1234-abcdabcdabcd"
