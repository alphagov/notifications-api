from boto3 import resource


def get_job_from_s3(bucket_name, job_id):
    s3 = resource('s3')
    key = s3.Object(bucket_name, '{}.csv'.format(job_id))
    return key.get()['Body'].read().decode('utf-8')
