from datetime import datetime, timedelta

from flask import current_app

import pytz
from boto3 import client, resource

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
    return remove_s3_object(bucket_name, file_location)


def get_s3_bucket_objects(bucket_name, subfolder='', older_than=7, limit_days=2):
    boto_client = client('s3', current_app.config['AWS_REGION'])
    paginator = boto_client.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(
        Bucket=bucket_name,
        Prefix=subfolder
    )

    all_objects_in_bucket = []
    for page in page_iterator:
        all_objects_in_bucket.extend(page['Contents'])

    return all_objects_in_bucket


def filter_s3_bucket_objects_within_date_range(bucket_objects, older_than=7, limit_days=2):
    """
    S3 returns the Object['LastModified'] as an 'offset-aware' timestamp so the
    date range filter must take this into account.

    Additionally an additional Object is returned by S3 corresponding to the
    container directory. This is redundant and should be removed.

    """
    end_date = datetime.now(tz=pytz.utc) - timedelta(days=older_than)
    start_date = end_date - timedelta(days=limit_days)
    filtered_items = [item for item in bucket_objects if all([
        not item['Key'].endswith('/'),
        item['LastModified'] > start_date,
        item['LastModified'] < end_date
    ])]

    return filtered_items


def remove_s3_object(bucket_name, object_key):
    obj = get_s3_object(bucket_name, object_key)
    return obj.delete()


def remove_transformed_dvla_file(job_id):
    bucket_name = current_app.config['DVLA_UPLOAD_BUCKET_NAME']
    file_location = '{}-dvla-job.text'.format(job_id)
    obj = get_s3_object(bucket_name, file_location)
    return obj.delete()
