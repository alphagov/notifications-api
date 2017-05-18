from boto3 import resource
from flask import current_app

FILE_LOCATION_STRUCTURE = 'service-{}-notify/{}.csv'


def get_s3_file(bucket_name, file_location):
    s3_file = get_s3_object(bucket_name, file_location)
    return s3_file.get()['Body'].read().decode('utf-8')


def get_s3_object(bucket_name, file_location):
    s3 = resource('s3')
    return s3.Object(bucket_name, file_location)


def get_job_from_s3(service_id, job_id):
    bucket_name = current_app.config['CSV_UPLOAD_BUCKET_NAME']
    file_location = FILE_LOCATION_STRUCTURE.format(service_id, job_id)
    obj = get_s3_object(bucket_name, file_location)
    return obj.get()['Body'].read().decode('utf-8')


def remove_job_from_s3(service_id, job_id):
    bucket_name = current_app.config['CSV_UPLOAD_BUCKET_NAME']
    file_location = FILE_LOCATION_STRUCTURE.format(service_id, job_id)
    obj = get_s3_object(bucket_name, file_location)
    return obj.delete()
