from datetime import datetime

from flask import json

from app.schema_validation import validate
from app.service.service_notification_schema import notification_for_service_no_content
from tests import create_authorization_header
from tests.app.db import create_service, create_notification, create_template, create_job


def test_get_notifications_for_service(client, notify_db_session):
    service = create_service()
    sms_template = create_template(service=service)
    email_template = create_template(service=service, template_type='email')
    email_template2 = create_template(service=service, template_type='email', content="with ((some)) placeholders")
    create_template(service=service, template_type='letter')
    job = create_job(template=sms_template)
    create_notification(template=sms_template, status='sending', sent_at=datetime.utcnow(),
                        updated_at=datetime.utcnow())
    create_notification(template=sms_template, status='created', created_by_id=service.users[0].id)
    create_notification(template=email_template, status='temporary-failure',
                        sent_at=datetime.utcnow(), updated_at=datetime.utcnow())
    create_notification(template=sms_template, status='delivered',
                        sent_at=datetime.utcnow(), updated_at=datetime.utcnow())
    create_notification(template=email_template2, job=job, job_row_number=1, personalisation={"some": "any"})

    auth_header = create_authorization_header()
    response = client.get(
        path='/service/{}/notifications/csv'.format(
            service.id
        ),
        headers=[auth_header]
    )

    results = json.loads(response.get_data(as_text=True))['notifications']
    for n in results:
        assert n == validate(n, notification_for_service_no_content)
