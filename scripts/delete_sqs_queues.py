import boto3
import csv
from datetime import datetime
from pprint import pprint
import os

client = boto3.client('sqs', region_name=os.getenv('AWS_REGION'))


def _formatted_date_from_timestamp(timestamp):
    return datetime.fromtimestamp(
        int(timestamp)
    ).strftime('%Y-%m-%d %H:%M:%S')


def get_queues():
    response = client.list_queues()
    queues = response['QueueUrls']
    return queues


def get_queue_attributes(queue_name):
    response = client.get_queue_attributes(
        QueueUrl=queue_name,
        AttributeNames=[
            'All'
        ]
    )
    queue_attributes = response['Attributes']
    return queue_attributes


def delete_queue(queue_name):
    response = client.delete_queue(
        QueueUrl=queue_name
    )
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        print('Deleted queue successfully')
    else:
        print('Error occured when attempting to delete queue')
        pprint(response)
    return response


def output_to_csv(queue_attributes):
    csv_name = 'queues.csv'
    with open(csv_name, 'w') as csvfile:
        fieldnames = [
            'Queue Name',
            'Number of Messages',
            'Number of Messages Delayed',
            'Number of Messages Not Visible',
            'Created'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for queue_attr in queue_attributes:
            queue_url = client.get_queue_url(
                QueueName=queue_attr['QueueArn']
            )['QueueUrl']
            writer.writerow({
                'Queue Name': queue_attr['QueueArn'],
                'Queue URL': queue_url,
                'Number of Messages': queue_attr['ApproximateNumberOfMessages'],
                'Number of Messages Delayed': queue_attr['ApproximateNumberOfMessagesDelayed'],
                'Number of Messages Not Visible': queue_attr['ApproximateNumberOfMessagesNotVisible'],
                'Created': _formatted_date_from_timestamp(queue_attr['CreatedTimestamp'])
            })
    return csv_name


def read_from_csv(csv_name):
    queue_urls = []
    with open(csv_name, 'r') as csvfile:
        next(csvfile)
        rows = csv.reader(csvfile, delimiter=',')
        for row in rows:
            queue_urls.append(row[1])
    return queue_urls


queues = get_queues()
for queue in queues:
    delete_queue(queue)
