from datetime import timedelta

import pytest
from freezegun import freeze_time
from pytest_mock import MockerFixture

from app.otel_metrics.provider import _request_duration, record_request_duration


def test_record_request_duration(mocker: MockerFixture) -> None:
    with freeze_time() as frozen_time:
        record_mock = mocker.patch.object(_request_duration, "record")

        @record_request_duration("email", "ses")
        def foo() -> None:
            frozen_time.tick(timedelta(seconds=42))
            raise RuntimeError

        with pytest.raises(RuntimeError):
            foo()

        record_mock.assert_called_once_with(
            42.0,
            {
                "error.type": "builtins.RuntimeError",
                "notification.type": "email",
                "provider.name": "ses",
            },
        )
