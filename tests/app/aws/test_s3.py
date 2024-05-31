from datetime import UTC, datetime, timedelta

import pytest
import pytz
from freezegun import freeze_time

from app.aws.s3 import get_list_of_files_by_suffix, get_s3_file
from tests.app.conftest import datetime_in_past


def single_s3_object_stub(key="foo", last_modified=None):
    return {
        "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',
        "Key": key,
        "LastModified": last_modified or datetime.now(UTC).replace(tzinfo=None),
    }


def test_get_s3_file_makes_correct_call(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    get_s3_file("foo-bucket", "bar-file.txt")

    get_s3_mock.assert_called_with("foo-bucket", "bar-file.txt")


@freeze_time("2018-01-11 00:00:00")
@pytest.mark.parametrize(
    "suffix_str, days_before, returned_no",
    [
        (".ACK.txt", None, 1),
        (".ack.txt", None, 1),
        (".ACK.TXT", None, 1),
        ("", None, 2),
        ("", 1, 1),
    ],
)
def test_get_list_of_files_by_suffix(notify_api, mocker, suffix_str, days_before, returned_no):
    paginator_mock = mocker.patch("app.aws.s3.client")
    multiple_pages_s3_object = [
        {
            "Contents": [
                single_s3_object_stub("bar/foo.ACK.txt", datetime_in_past(1, 0)),
            ]
        },
        {
            "Contents": [
                single_s3_object_stub("bar/foo1.rs.txt", datetime_in_past(2, 0)),
            ]
        },
    ]
    paginator_mock.return_value.get_paginator.return_value.paginate.return_value = multiple_pages_s3_object
    if days_before:
        key = get_list_of_files_by_suffix(
            "foo-bucket",
            subfolder="bar",
            suffix=suffix_str,
            last_modified=datetime.now(tz=pytz.utc) - timedelta(days=days_before),
        )
    else:
        key = get_list_of_files_by_suffix("foo-bucket", subfolder="bar", suffix=suffix_str)

    assert sum(1 for x in key) == returned_no
    for k in key:
        assert k == "bar/foo.ACK.txt"


def test_get_list_of_files_by_suffix_empty_contents_return_with_no_error(notify_api, mocker):
    paginator_mock = mocker.patch("app.aws.s3.client")
    multiple_pages_s3_object = [
        {
            "other_content": [
                "some_values",
            ]
        }
    ]
    paginator_mock.return_value.get_paginator.return_value.paginate.return_value = multiple_pages_s3_object
    key = get_list_of_files_by_suffix("foo-bucket", subfolder="bar", suffix=".pdf")

    assert sum(1 for x in key) == 0
