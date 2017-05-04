from boto3 import resource
from flask import current_app

FILE_LOCATION_STRUCTURE = 'service-{}-notify/{}.csv'


def get_s3_object(bucket_name, file_location):
    s3 = resource('s3')
    s3_object = s3.Object(bucket_name, file_location)
    return s3_object.get()['Body'].read()


def get_job_from_s3(service_id, job_id):
    job = _job_from_s3(service_id, job_id)
    return job


def remove_job_from_s3(service_id, job_id):
    job = _job_from_s3(service_id, job_id)
    return job.delete()


def _job_from_s3():
    bucket_name = current_app.config['CSV_UPLOAD_BUCKET_NAME']
    file_location = FILE_LOCATION_STRUCTURE.format(service_id, job_id)
    obj = get_s3_object(bucket_name, file_location).decode('utf-8')
    return obj
