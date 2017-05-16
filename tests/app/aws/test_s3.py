from app.aws.s3 import get_s3_file


def test_get_s3_file_makes_correct_call(sample_service, sample_job, mocker):
    get_s3_mock = mocker.patch('app.aws.s3.get_s3_object')
    get_s3_file('foo-bucket', 'bar-file.txt')

    get_s3_mock.assert_called_with(
        'foo-bucket',
        'bar-file.txt'
    )
