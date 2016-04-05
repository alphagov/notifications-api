from boto3 import resource


def get_s3_job_object(bucket_name, job_id):
    s3 = resource('s3')
    return s3.Object(bucket_name, '{}.csv'.format(job_id))


def get_job_from_s3(bucket_name, job_id):
    obj = get_s3_job_object(bucket_name, job_id)
    return obj.get()['Body'].read().decode('utf-8')


def remove_job_from_s3(bucket_name, job_id):
    obj = get_s3_job_object(bucket_name, job_id)
    return obj.delete()
