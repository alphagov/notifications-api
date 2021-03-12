import botocore
from boto3 import client, resource
from flask import current_app

FILE_LOCATION_STRUCTURE = 'service-{}-notify/{}.csv'


def get_s3_file(bucket_name, file_location):
    s3_file = get_s3_object(bucket_name, file_location)
    return s3_file.get()['Body'].read().decode('utf-8')


def get_s3_object(bucket_name, file_location):
    s3 = resource('s3')
    return s3.Object(bucket_name, file_location)


def head_s3_object(bucket_name, file_location):
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.head_object
    boto_client = client('s3', current_app.config['AWS_REGION'])
    return boto_client.head_object(Bucket=bucket_name, Key=file_location)


def file_exists(bucket_name, file_location):
    try:
        # try and access metadata of object
        get_s3_object(bucket_name, file_location).metadata
        return True
    except botocore.exceptions.ClientError as e:
        if e.response['ResponseMetadata']['HTTPStatusCode'] == 404:
            return False
        raise


def get_job_location(service_id, job_id):
    return (
        current_app.config['CSV_UPLOAD_BUCKET_NAME'],
        FILE_LOCATION_STRUCTURE.format(service_id, job_id),
    )


def get_contact_list_location(service_id, contact_list_id):
    return (
        current_app.config['CONTACT_LIST_BUCKET_NAME'],
        FILE_LOCATION_STRUCTURE.format(service_id, contact_list_id),
    )


def get_job_and_metadata_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()['Body'].read().decode('utf-8'), obj.get()['Metadata']


def get_job_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()['Body'].read().decode('utf-8')


def get_job_metadata_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()['Metadata']


def remove_job_from_s3(service_id, job_id):
    return remove_s3_object(*get_job_location(service_id, job_id))


def remove_contact_list_from_s3(service_id, contact_list_id):
    return remove_s3_object(*get_contact_list_location(service_id, contact_list_id))


def get_s3_bucket_objects(bucket_name, subfolder=''):
    boto_client = client('s3', current_app.config['AWS_REGION'])
    paginator = boto_client.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(
        Bucket=bucket_name,
        Prefix=subfolder
    )

    all_objects_in_bucket = []
    for page in page_iterator:
        if page.get('Contents'):
            all_objects_in_bucket.extend(page['Contents'])

    return all_objects_in_bucket


def remove_s3_object(bucket_name, object_key):
    obj = get_s3_object(bucket_name, object_key)
    return obj.delete()


def get_list_of_files_by_suffix(bucket_name, subfolder='', suffix='', last_modified=None):
    s3_client = client('s3', current_app.config['AWS_REGION'])
    paginator = s3_client.get_paginator('list_objects_v2')

    page_iterator = paginator.paginate(
        Bucket=bucket_name,
        Prefix=subfolder
    )

    for page in page_iterator:
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.lower().endswith(suffix.lower()):
                if not last_modified or obj['LastModified'] >= last_modified:
                    yield key
