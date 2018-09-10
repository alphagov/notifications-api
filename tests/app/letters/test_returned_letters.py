import pytest


@pytest.mark.parametrize('status, references', [
    (200, ["1234567890ABCDEF", "1234567890ABCDEG"]),
    (400, ["1234567890ABCDEFG", "1234567890ABCDEG"]),
    (400, ["1234567890ABCDE", "1234567890ABCDEG"]),
    (400, ["1234567890ABCDE\u26d4", "1234567890ABCDEG"]),
    (400, ["NOTIFY0001234567890ABCDEF", "1234567890ABCDEG"]),
])
def test_process_returned_letters(status, references, admin_request, mocker):
    mock_celery = mocker.patch("app.letters.rest.process_returned_letters_list.apply_async")

    response = admin_request.post(
        'letter-job.create_process_returned_letters_job',
        _data={"references": references},
        _expected_status=status
    )

    if status != 200:
        assert '{} does not match'.format(references[0]) in response['errors'][0]['message']
    else:
        mock_celery.assert_called_once_with([references], queue='database-tasks')
