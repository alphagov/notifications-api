"""

Script to manage SQS queues. Can list or delete queues.

Uses boto, so relies on correctly set up AWS access keys and tokens.

In principle use this script to dump details of all queues in a gievn environment, and then 
manipulate the resultant CSV file so that it contains the queues you want to delete.

Very hands on. Starter for a more automagic process.

Usage:
    scripts/delete_sqs_queues.py <action>
    
    options are:
    - list: dumps queue details to local file queues.csv in current directory.
    - delete: delete queues from local file queues.csv in current directory.

Example:
        scripts/delete_sqs_queues.py list delete 
"""

from docopt import docopt
import boto3
import csv
from datetime import datetime

FILE_NAME = "/tmp/queues.csv"

client = boto3.client('sqs', region_name='eu-west-1')


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
    queue_attributes.update({
       'QueueUrl': queue_name
    })
    return queue_attributes


def delete_queue(queue_url):
    print("DELETEING {}".format(queue_url))
    response = client.delete_queue(
        QueueUrl=queue_url
    )
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        print('Deleted queue successfully {}'.format(response['ResponseMetadata']))
    else:
        print('Error occured when attempting to delete queue')
        pprint(response)
    return response


def output_to_csv(queue_attributes):
    with open(FILE_NAME, 'w') as csvfile:
        fieldnames = [
            'Queue Name',
            'Queue URL',
            'Number of Messages',
            'Number of Messages Delayed',
            'Number of Messages Not Visible',
            'Created'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for queue_attr in queue_attributes:
            writer.writerow({
                'Queue Name': queue_attr['QueueArn'],
                'Queue URL': queue_attr['QueueUrl'],
                'Number of Messages': queue_attr['ApproximateNumberOfMessages'],
                'Number of Messages Delayed': queue_attr['ApproximateNumberOfMessagesDelayed'],
                'Number of Messages Not Visible': queue_attr['ApproximateNumberOfMessagesNotVisible'],
                'Created': _formatted_date_from_timestamp(queue_attr['CreatedTimestamp'])
            })


def read_from_csv():
    queue_urls = []
    with open(FILE_NAME, 'r') as csvfile:
        next(csvfile)
        rows = csv.reader(csvfile, delimiter=',')
        for row in rows:
            queue_urls.append(row[1])
    return queue_urls


if __name__ == "__main__":
    arguments = docopt(__doc__)

    if arguments['<action>'] == 'list':
        queues = get_queues()
        queue_attributes = []
        for queue in queues:
            queue_attributes.append(get_queue_attributes(queue))
        output_to_csv(queue_attributes)
    elif arguments['<action>'] == 'delete':
        queues_to_delete = read_from_csv()
        for queue in queues_to_delete:
            delete_queue(queue)
    else:
        print("UNKNOWN COMMAND")
        exit(1)
