from unittest.mock import call

from flask import current_app

from app.aws.s3 import get_s3_file, remove_transformed_dvla_file


def test_get_s3_file_makes_correct_call(notify_api, mocker):
    get_s3_mock = mocker.patch('app.aws.s3.get_s3_object')
    get_s3_file('foo-bucket', 'bar-file.txt')

    get_s3_mock.assert_called_with(
        'foo-bucket',
        'bar-file.txt'
    )


def test_remove_transformed_dvla_file_makes_correct_call(notify_api, mocker):
    s3_mock = mocker.patch('app.aws.s3.get_s3_object')
    fake_uuid = '5fbf9799-6b9b-4dbb-9a4e-74a939f3bb49'

    remove_transformed_dvla_file(fake_uuid)

    s3_mock.assert_has_calls([
        call(current_app.config['DVLA_UPLOAD_BUCKET_NAME'], '{}-dvla-job.text'.format(fake_uuid)),
        call().delete()
    ])
