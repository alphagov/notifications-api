import botocore
from boto3 import resource
from flask import current_app

FILE_LOCATION_STRUCTURE = "service-{}-notify/{}.csv"


def get_s3_object(bucket_name, file_location):
    s3 = resource("s3")
    return s3.Object(bucket_name, file_location)


def file_exists(bucket_name, file_location):
    try:
        # try and access metadata of object
        get_s3_object(bucket_name, file_location).metadata  # noqa: B018
        return True
    except botocore.exceptions.ClientError as e:
        if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
            return False
        raise


def get_job_location(service_id, job_id):
    return (
        current_app.config["S3_BUCKET_CSV_UPLOAD"],
        FILE_LOCATION_STRUCTURE.format(service_id, job_id),
    )


def get_contact_list_location(service_id, contact_list_id):
    return (
        current_app.config["S3_BUCKET_CONTACT_LIST"],
        FILE_LOCATION_STRUCTURE.format(service_id, contact_list_id),
    )


def get_job_and_metadata_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()["Body"].read().decode("utf-8"), obj.get()["Metadata"]


def get_job_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()["Body"].read().decode("utf-8")


def get_job_metadata_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()["Metadata"]


def remove_job_from_s3(service_id, job_id):
    return remove_s3_object(*get_job_location(service_id, job_id))


def remove_contact_list_from_s3(service_id, contact_list_id):
    return remove_s3_object(*get_contact_list_location(service_id, contact_list_id))


def remove_s3_object(bucket_name, object_key):
    obj = get_s3_object(bucket_name, object_key)
    return obj.delete()
