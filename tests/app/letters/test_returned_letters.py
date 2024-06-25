import pytest


@pytest.mark.parametrize(
    "status, references",
    [
        (200, ["1234567890ABCDEF", "1234567890ABCDEG"]),
        (400, ["1234567890ABCDEFG", "1234567890ABCDEG"]),
        (400, ["1234567890ABCDE", "1234567890ABCDEG"]),
        (400, ["1234567890ABCDE\u26d4", "1234567890ABCDEG"]),
        (400, ["NOTIFY0001234567890ABCDEF", "1234567890ABCDEG"]),
    ],
)
def test_process_returned_letters(status, references, admin_request, mocker):
    mock_celery = mocker.patch("app.letters.rest.process_returned_letters_list.apply_async")

    response = admin_request.post(
        "letter-job.create_process_returned_letters_job", _data={"references": references}, _expected_status=status
    )

    if status != 200:
        assert f"{references[0]} does not match" in response["errors"][0]["message"]
    else:
        mock_celery.assert_called_once_with(args=(references,), queue="database-tasks", compression="zlib")


def test_process_returned_letters_splits_tasks_up(admin_request, mocker):
    mock_celery = mocker.patch("app.letters.rest.process_returned_letters_list.apply_async")
    mocker.patch("app.letters.rest.MAX_REFERENCES_PER_TASK", 3)

    references = [f"{x:016}" for x in range(10)]

    admin_request.post(
        "letter-job.create_process_returned_letters_job",
        _data={"references": references},
    )

    assert mock_celery.call_count == 4

    assert mock_celery.call_args_list[0][1]["args"][0] == ["0000000000000000", "0000000000000001", "0000000000000002"]
    assert mock_celery.call_args_list[1][1]["args"][0] == ["0000000000000003", "0000000000000004", "0000000000000005"]
    assert mock_celery.call_args_list[2][1]["args"][0] == ["0000000000000006", "0000000000000007", "0000000000000008"]
    assert mock_celery.call_args_list[3][1]["args"][0] == ["0000000000000009"]
