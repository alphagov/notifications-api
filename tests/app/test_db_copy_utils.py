from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.db_copy_utils import (
    build_notifications_copy_query,
    execute_copy_to_bytes,
    get_notifications_csv_chunk,
)


class TestBuildNotificationsCopyQuery:
    def test_basic_query_structure(self):
        service_id = uuid4()
        query = build_notifications_copy_query(
            service_id=service_id,
            notification_type="sms",
            notification_statuses=["delivered", "sent"],
            limit_days=7,
            chunk_size=1000,
        )

        assert "SELECT" in query
        assert "FROM notifications" in query
        assert "templates_history" in query
        assert str(service_id) in query
        assert "notification_type = 'sms'" in query
        assert "delivered" in query
        assert "sent" in query
        assert "LIMIT 1000" in query

    @patch("app.dao.notifications_dao.db")
    def test_query_with_older_than_id(self, mock_db):
        service_id = uuid4()
        older_than_id = uuid4()

        mock_db.session.query.return_value.filter.return_value.scalar.return_value = "2023-01-01 00:00:00"

        query = build_notifications_copy_query(
            service_id=service_id,
            notification_type="email",
            notification_statuses=[],
            limit_days=14,
            chunk_size=500,
            older_than_id=older_than_id,
        )

        assert "notifications.created_at, notifications.id" in query
        assert "2023-01-01 00:00:00" in query
        assert "notifications.created_at >=" in query

    def test_query_excludes_test_keys(self):
        query = build_notifications_copy_query(
            service_id=uuid4(),
            notification_type="sms",
            notification_statuses=[],
            limit_days=7,
            chunk_size=100,
        )

        assert "key_type != 'test'" in query

    def test_query_includes_all_columns(self):
        query = build_notifications_copy_query(
            service_id=uuid4(),
            notification_type="email",
            notification_statuses=[],
            limit_days=7,
            chunk_size=100,
        )

        expected_columns = [
            '"Recipient"',
            '"Reference"',
            '"Template"',
            '"Type"',
            '"Sent by"',
            '"Sent by email"',
            '"Job"',
            '"Status"',
            '"Time"',
            '"API key name"',
            "id",
            "created_at",
        ]

        for column in expected_columns:
            assert column in query, f"Expected column {column} not found in query"


class TestExecuteCopyToBytes:
    @patch("app.db_copy_utils.db")
    def test_executes_query_and_copy_command(self, mock_db):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.engine.raw_connection.return_value = mock_conn

        sample_id = uuid4()
        mock_cursor.fetchall.return_value = [
            (
                "recipient@example.com",
                "ref123",
                "Template",
                "email",
                "User",
                "user@example.com",
                "job.csv",
                "delivered",
                "2023-01-01 10:00:00",
                "api_key",
                sample_id,
                "2023-01-01 10:00:00",
            ),
        ]

        def copy_expert_side_effect(sql, buffer):
            csv_data = (
                b"Recipient,Reference,Template,Type,Sent by,Sent by email,Job,Status,Time,API key name\n"
                b"recipient@example.com,ref123,Template,email,User,user@example.com,job.csv,delivered,"
                b"2023-01-01 10:00:00,api_key\n"
            )
            buffer.write(csv_data)

        mock_cursor.copy_expert.side_effect = copy_expert_side_effect

        query = "SELECT * FROM notifications LIMIT 10"
        csv_bytes, last_id, row_count = execute_copy_to_bytes(query, include_header=True)

        assert csv_bytes is not None
        assert len(csv_bytes) > 0
        assert b"Recipient" in csv_bytes
        assert b"recipient@example.com" in csv_bytes
        assert last_id == sample_id
        assert row_count == 1
        mock_conn.close.assert_called_once()

    @patch("app.db_copy_utils.db")
    def test_handles_empty_result_set(self, mock_db):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.engine.raw_connection.return_value = mock_conn

        mock_cursor.fetchall.return_value = []

        def copy_expert_side_effect(sql, buffer):
            buffer.write(b"Recipient,Reference,Template,Type,Sent by,Sent by email,Job,Status,Time,API key name\n")

        mock_cursor.copy_expert.side_effect = copy_expert_side_effect

        query = "SELECT * FROM notifications WHERE 1=0"
        csv_bytes, last_id, row_count = execute_copy_to_bytes(query, include_header=True)

        assert last_id is None
        assert row_count == 0
        assert csv_bytes is not None
        mock_conn.close.assert_called_once()

    @patch("app.db_copy_utils.db")
    def test_excludes_header_when_requested(self, mock_db):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.engine.raw_connection.return_value = mock_conn

        sample_id = uuid4()
        mock_cursor.fetchall.return_value = [
            (
                "test@example.com",
                "",
                "Template",
                "email",
                "",
                "",
                "",
                "delivered",
                "2023-01-01",
                "",
                sample_id,
                "2023-01-01",
            ),
        ]

        def copy_expert_side_effect(sql, buffer):
            assert "HEADER" not in sql
            buffer.write(b"test@example.com,,Template,email,,,,delivered,2023-01-01,\n")

        mock_cursor.copy_expert.side_effect = copy_expert_side_effect

        query = "SELECT * FROM notifications LIMIT 1"
        csv_bytes, last_id, row_count = execute_copy_to_bytes(query, include_header=False)

        assert b"Recipient" not in csv_bytes
        assert b"test@example.com" in csv_bytes
        mock_conn.close.assert_called_once()


class TestGetNotificationsCSVChunk:
    @patch("app.db_copy_utils.execute_copy_to_bytes")
    @patch("app.db_copy_utils.build_notifications_copy_query")
    def test_calls_build_query_and_execute(self, mock_build_query, mock_execute):
        service_id = uuid4()
        sample_id = uuid4()
        mock_build_query.return_value = "SELECT * FROM notifications"
        mock_execute.return_value = (b"csv,data\n", sample_id, 100)

        csv_bytes, last_id, row_count = get_notifications_csv_chunk(
            service_id=service_id,
            notification_type="sms",
            notification_status_filter="all",
            limit_days=7,
            chunk_size=1000,
            older_than_id=None,
            include_header=True,
        )

        mock_build_query.assert_called_once()
        mock_execute.assert_called_once_with("SELECT * FROM notifications", include_header=True)
        assert csv_bytes == b"csv,data\n"
        assert last_id == sample_id
        assert row_count == 100

    @patch("app.db_copy_utils.execute_copy_to_bytes")
    @patch("app.db_copy_utils.build_notifications_copy_query")
    def test_passes_pagination_parameters(self, mock_build_query, mock_execute):
        service_id = uuid4()
        older_than_id = uuid4()
        mock_build_query.return_value = "SELECT * FROM notifications"
        mock_execute.return_value = (b"", None, 0)

        get_notifications_csv_chunk(
            service_id=service_id,
            notification_type="email",
            notification_status_filter="delivered",
            limit_days=14,
            chunk_size=500,
            older_than_id=older_than_id,
            include_header=False,
        )

        call_args = mock_build_query.call_args
        assert call_args[1]["service_id"] == service_id
        assert call_args[1]["notification_type"] == "email"
        assert call_args[1]["limit_days"] == 14
        assert call_args[1]["chunk_size"] == 500
        assert call_args[1]["older_than_id"] == older_than_id

        mock_execute.assert_called_once_with("SELECT * FROM notifications", include_header=False)
