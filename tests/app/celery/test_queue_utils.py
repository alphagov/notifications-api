from app.celery.queue_utils import get_message_group_id_for_queue
from app.config import QueueNames
from tests.conftest import set_config


def test_get_message_group_id_for_queue_disabled_flag_returns_empty(notify_api):
    with set_config(notify_api, "ENABLE_SQS_FAIR_GROUPING", False):
        assert (
            get_message_group_id_for_queue(
                queue_name=QueueNames.JOBS,
                service_id="service-123",
            )
            == {}
        )


def test_queue_without_grouping_rules_returns_empty(notify_api, enable_sqs_fair_grouping):
    assert (
        get_message_group_id_for_queue(
            queue_name=QueueNames.PERIODIC,
            service_id="service-123",
        )
        == {}
    )


def test_database_queue_groups_with_service_id_only(notify_api, enable_sqs_fair_grouping):
    result = get_message_group_id_for_queue(
        queue_name=QueueNames.DATABASE,
        service_id="service-123",
    )

    assert result == {"MessageGroupId": "service-123"}


def test_missing_optional_dimension_does_not_disable_grouping(notify_api, enable_sqs_fair_grouping):
    result = get_message_group_id_for_queue(
        queue_name=QueueNames.SEND_SMS,
        service_id="service-123",
        origin="api",
        # key_type missing
    )

    assert result == {"MessageGroupId": "service-123#api"}


def test_no_dimensions_available_returns_empty(notify_api, enable_sqs_fair_grouping):
    assert (
        get_message_group_id_for_queue(
            queue_name=QueueNames.SEND_SMS,
        )
        == {}
    )
