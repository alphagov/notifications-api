import uuid
import boto3
from itsdangerous import URLSafeSerializer
from flask import current_app


def add_notification_to_queue(service_id, template_id, type_, notification):
    q = boto3.resource(
        'sqs', region_name=current_app.config['AWS_REGION']
    ).create_queue(QueueName=str(service_id))
    message_id = str(uuid.uuid4())
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))
    encrypted = serializer.dumps(notification, current_app.config.get('DANGEROUS_SALT'))
    q.send_message(MessageBody=encrypted,
                   MessageAttributes={'type': {'StringValue': type_, 'DataType': 'String'},
                                      'message_id': {'StringValue': message_id, 'DataType': 'String'},
                                      'service_id': {'StringValue': str(service_id), 'DataType': 'String'},
                                      'template_id': {'StringValue': str(template_id), 'DataType': 'String'}})
