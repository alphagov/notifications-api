from datetime import datetime, date
import uuid

from app import db
from app.dao.jobs_dao import dao_create_job
from app.dao.service_data_retention_dao import insert_service_data_retention
from app.dao.service_inbound_api_dao import save_service_inbound_api
from app.dao.service_callback_api_dao import save_service_callback_api
from app.dao.service_sms_sender_dao import update_existing_sms_sender_with_inbound_number, dao_update_service_sms_sender
from app.dao.invited_org_user_dao import save_invited_org_user
from app.models import (
    ApiKey,
    DailySortedLetter,
    InboundSms,
    InboundNumber,
    Job,
    Notification,
    EmailBranding,
    Organisation,
    Rate,
    Service,
    ServiceEmailReplyTo,
    ServiceInboundApi,
    ServiceCallbackApi,
    ServiceLetterContact,
    ScheduledNotification,
    ServicePermission,
    ServiceSmsSender,
    Template,
    User,
    EMAIL_TYPE,
    SMS_TYPE,
    KEY_TYPE_NORMAL,
    AnnualBilling,
    InvitedOrganisationUser,
    FactBilling,
    FactNotificationStatus,
    Complaint,
)
from app.dao.users_dao import save_model_user
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_created_scheduled_notification
)
from app.dao.templates_dao import dao_create_template
from app.dao.services_dao import dao_create_service
from app.dao.service_permissions_dao import dao_add_service_permission
from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.dao.email_branding_dao import dao_create_email_branding
from app.dao.organisation_dao import dao_create_organisation


def create_user(mobile_number="+447700900986", email="notify@digital.cabinet-office.gov.uk", state='active', id_=None):
    data = {
        'id': id_ or uuid.uuid4(),
        'name': 'Test User',
        'email_address': email,
        'password': 'password',
        'mobile_number': mobile_number,
        'state': state
    }
    user = User.query.filter_by(email_address=email).first()
    if not user:
        user = User(**data)
    save_model_user(user)
    return user


def create_service(
        user=None,
        service_name="Sample service",
        service_id=None,
        restricted=False,
        service_permissions=[EMAIL_TYPE, SMS_TYPE],
        research_mode=False,
        active=True,
        email_from=None,
        prefix_sms=True,
        message_limit=1000,
        organisation_type='central',
        branding=None
):
    service = Service(
        name=service_name,
        message_limit=message_limit,
        restricted=restricted,
        email_from=email_from if email_from else service_name.lower().replace(' ', '.'),
        created_by=user or create_user(email='{}@digital.cabinet-office.gov.uk'.format(uuid.uuid4())),
        prefix_sms=prefix_sms,
        organisation_type=organisation_type,
        branding=branding
    )

    dao_create_service(service, service.created_by, service_id, service_permissions=service_permissions)

    service.active = active
    service.research_mode = research_mode

    return service


def create_service_with_inbound_number(
        inbound_number='1234567',
        *args, **kwargs
):
    service = create_service(*args, **kwargs)

    sms_sender = ServiceSmsSender.query.filter_by(service_id=service.id).first()
    inbound = create_inbound_number(number=inbound_number, service_id=service.id)
    update_existing_sms_sender_with_inbound_number(service_sms_sender=sms_sender,
                                                   sms_sender=inbound_number,
                                                   inbound_number_id=inbound.id)

    return service


def create_service_with_defined_sms_sender(
        sms_sender_value='1234567',
        *args, **kwargs
):
    service = create_service(*args, **kwargs)

    sms_sender = ServiceSmsSender.query.filter_by(service_id=service.id).first()
    dao_update_service_sms_sender(service_id=service.id,
                                  service_sms_sender_id=sms_sender.id,
                                  is_default=True,
                                  sms_sender=sms_sender_value)

    return service


def create_template(
        service,
        template_type=SMS_TYPE,
        template_name=None,
        subject='Template subject',
        content='Dear Sir/Madam, Hello. Yours Truly, The Government.',
        reply_to=None,
        hidden=False
):
    data = {
        'name': template_name or '{} Template Name'.format(template_type),
        'template_type': template_type,
        'content': content,
        'service': service,
        'created_by': service.created_by,
        'reply_to': reply_to,
        'hidden': hidden
    }
    if template_type != SMS_TYPE:
        data['subject'] = subject
    template = Template(**data)
    dao_create_template(template)
    return template


def create_notification(
        template,
        job=None,
        job_row_number=None,
        to_field=None,
        status='created',
        reference=None,
        created_at=None,
        sent_at=None,
        updated_at=None,
        billable_units=1,
        personalisation=None,
        api_key=None,
        key_type=KEY_TYPE_NORMAL,
        sent_by=None,
        client_reference=None,
        rate_multiplier=None,
        international=False,
        phone_prefix=None,
        scheduled_for=None,
        normalised_to=None,
        one_off=False,
        sms_sender_id=None,
        reply_to_text=None,
        created_by_id=None
):
    if created_at is None:
        created_at = datetime.utcnow()

    if to_field is None:
        to_field = '+447700900855' if template.template_type == SMS_TYPE else 'test@example.com'

    if status != 'created':
        sent_at = sent_at or datetime.utcnow()
        updated_at = updated_at or datetime.utcnow()

    if not one_off and (job is None and api_key is None):
        # we didn't specify in test - lets create it
        api_key = ApiKey.query.filter(ApiKey.service == template.service, ApiKey.key_type == key_type).first()
        if not api_key:
            api_key = create_api_key(template.service, key_type=key_type)

    data = {
        'id': uuid.uuid4(),
        'to': to_field,
        'job_id': job and job.id,
        'job': job,
        'service_id': template.service.id,
        'service': template.service,
        'template_id': template.id,
        'template_version': template.version,
        'status': status,
        'reference': reference,
        'created_at': created_at,
        'sent_at': sent_at,
        'billable_units': billable_units,
        'personalisation': personalisation,
        'notification_type': template.template_type,
        'api_key': api_key,
        'api_key_id': api_key and api_key.id,
        'key_type': api_key.key_type if api_key else key_type,
        'sent_by': sent_by,
        'updated_at': updated_at,
        'client_reference': client_reference,
        'job_row_number': job_row_number,
        'rate_multiplier': rate_multiplier,
        'international': international,
        'phone_prefix': phone_prefix,
        'normalised_to': normalised_to,
        'reply_to_text': reply_to_text,
        'created_by_id': created_by_id
    }
    notification = Notification(**data)
    dao_create_notification(notification)
    if scheduled_for:
        scheduled_notification = ScheduledNotification(id=uuid.uuid4(),
                                                       notification_id=notification.id,
                                                       scheduled_for=datetime.strptime(scheduled_for,
                                                                                       "%Y-%m-%d %H:%M"))
        if status != 'created':
            scheduled_notification.pending = False
        dao_created_scheduled_notification(scheduled_notification)

    return notification


def create_job(
        template,
        notification_count=1,
        created_at=None,
        job_status='pending',
        scheduled_for=None,
        processing_started=None,
        original_file_name='some.csv'
):
    data = {
        'id': uuid.uuid4(),
        'service_id': template.service_id,
        'service': template.service,
        'template_id': template.id,
        'template_version': template.version,
        'original_file_name': original_file_name,
        'notification_count': notification_count,
        'created_at': created_at or datetime.utcnow(),
        'created_by': template.created_by,
        'job_status': job_status,
        'scheduled_for': scheduled_for,
        'processing_started': processing_started
    }
    job = Job(**data)
    dao_create_job(job)
    return job


def create_service_permission(service_id, permission=EMAIL_TYPE):
    dao_add_service_permission(
        service_id if service_id else create_service().id, permission)

    service_permissions = ServicePermission.query.all()

    return service_permissions


def create_inbound_sms(
        service,
        notify_number=None,
        user_number='447700900111',
        provider_date=None,
        provider_reference=None,
        content='Hello',
        provider="mmg",
        created_at=None
):
    inbound = InboundSms(
        service=service,
        created_at=created_at or datetime.utcnow(),
        notify_number=notify_number or service.get_default_sms_sender(),
        user_number=user_number,
        provider_date=provider_date or datetime.utcnow(),
        provider_reference=provider_reference or 'foo',
        content=content,
        provider=provider
    )
    dao_create_inbound_sms(inbound)
    return inbound


def create_service_inbound_api(
        service,
        url="https://something.com",
        bearer_token="some_super_secret",
):
    service_inbound_api = ServiceInboundApi(service_id=service.id,
                                            url=url,
                                            bearer_token=bearer_token,
                                            updated_by_id=service.users[0].id
                                            )
    save_service_inbound_api(service_inbound_api)
    return service_inbound_api


def create_service_callback_api(
        service,
        url="https://something.com",
        bearer_token="some_super_secret",
        callback_type="delivery_status"
):
    service_callback_api = ServiceCallbackApi(service_id=service.id,
                                              url=url,
                                              bearer_token=bearer_token,
                                              updated_by_id=service.users[0].id,
                                              callback_type=callback_type
                                              )
    save_service_callback_api(service_callback_api)
    return service_callback_api


def create_email_branding(colour='blue', logo='test_x2.png', name='test_org_1', text='DisplayName'):
    data = {
        'colour': colour,
        'logo': logo,
        'name': name,
        'text': text,
    }
    email_branding = EmailBranding(**data)
    dao_create_email_branding(email_branding)

    return email_branding


def create_rate(start_date, value, notification_type):
    rate = Rate(
        id=uuid.uuid4(),
        valid_from=start_date,
        rate=value,
        notification_type=notification_type
    )
    db.session.add(rate)
    db.session.commit()
    return rate


def create_api_key(service, key_type=KEY_TYPE_NORMAL):
    id_ = uuid.uuid4()
    api_key = ApiKey(
        service=service,
        name='{} api key {}'.format(key_type, id_),
        created_by=service.created_by,
        key_type=key_type,
        id=id_,
        secret=uuid.uuid4()
    )
    db.session.add(api_key)
    db.session.commit()
    return api_key


def create_inbound_number(number, provider='mmg', active=True, service_id=None):
    inbound_number = InboundNumber(
        id=uuid.uuid4(),
        number=number,
        provider=provider,
        active=active,
        service_id=service_id
    )
    db.session.add(inbound_number)
    db.session.commit()
    return inbound_number


def create_reply_to_email(
        service,
        email_address,
        is_default=True,
        archived=False
):
    data = {
        'service': service,
        'email_address': email_address,
        'is_default': is_default,
        'archived': archived,
    }
    reply_to = ServiceEmailReplyTo(**data)

    db.session.add(reply_to)
    db.session.commit()

    return reply_to


def create_service_sms_sender(
        service,
        sms_sender,
        is_default=True,
        inbound_number_id=None,
        archived=False
):
    data = {
        'service_id': service.id,
        'sms_sender': sms_sender,
        'is_default': is_default,
        'inbound_number_id': inbound_number_id,
        'archived': archived,
    }
    service_sms_sender = ServiceSmsSender(**data)

    db.session.add(service_sms_sender)
    db.session.commit()

    return service_sms_sender


def create_letter_contact(
        service,
        contact_block,
        is_default=True,
        archived=False
):
    data = {
        'service': service,
        'contact_block': contact_block,
        'is_default': is_default,
        'archived': archived,
    }
    letter_content = ServiceLetterContact(**data)

    db.session.add(letter_content)
    db.session.commit()

    return letter_content


def create_annual_billing(
        service_id, free_sms_fragment_limit, financial_year_start
):
    annual_billing = AnnualBilling(
        service_id=service_id,
        free_sms_fragment_limit=free_sms_fragment_limit,
        financial_year_start=financial_year_start
    )
    db.session.add(annual_billing)
    db.session.commit()

    return annual_billing


def create_organisation(name='test_org_1', active=True):
    data = {
        'name': name,
        'active': active
    }
    organisation = Organisation(**data)
    dao_create_organisation(organisation)

    return organisation


def create_invited_org_user(organisation, invited_by, email_address='invite@example.com'):
    invited_org_user = InvitedOrganisationUser(
        email_address=email_address,
        invited_by=invited_by,
        organisation=organisation,
    )
    save_invited_org_user(invited_org_user)
    return invited_org_user


def create_daily_sorted_letter(billing_day=date(2018, 1, 18),
                               file_name="Notify-20180118123.rs.txt",
                               unsorted_count=0,
                               sorted_count=0):
    daily_sorted_letter = DailySortedLetter(
        billing_day=billing_day,
        file_name=file_name,
        unsorted_count=unsorted_count,
        sorted_count=sorted_count
    )

    db.session.add(daily_sorted_letter)
    db.session.commit()

    return daily_sorted_letter


def create_ft_billing(bst_date,
                      notification_type,
                      template=None,
                      service=None,
                      provider='test',
                      rate_multiplier=1,
                      international=False,
                      rate=0,
                      billable_unit=1,
                      notifications_sent=1
                      ):
    if not service:
        service = create_service()
    if not template:
        template = create_template(service=service, template_type=notification_type)

    data = FactBilling(bst_date=bst_date,
                       service_id=service.id,
                       template_id=template.id,
                       notification_type=notification_type,
                       provider=provider,
                       rate_multiplier=rate_multiplier,
                       international=international,
                       rate=rate,
                       billable_units=billable_unit,
                       notifications_sent=notifications_sent)
    db.session.add(data)
    db.session.commit()
    return data


def create_ft_notification_status(
    bst_date,
    notification_type='sms',
    service=None,
    template=None,
    job=None,
    key_type='normal',
    notification_status='delivered',
    count=1
):
    if template:
        service = template.service
        notification_type = template.template_type
    else:
        if not service:
            service = create_service()
        template = create_template(service=service, template_type=notification_type)

    data = FactNotificationStatus(
        bst_date=bst_date,
        template_id=template.id,
        service_id=service.id,
        job_id=job.id if job else uuid.UUID(int=0),
        notification_type=notification_type,
        key_type=key_type,
        notification_status=notification_status,
        notification_count=count
    )
    db.session.add(data)
    db.session.commit()
    return data


def create_complaint(service=None,
                     notification=None,
                     created_at=None):
    if not service:
        service = create_service()
    if not notification:
        template = create_template(service=service, template_type='email')
        notification = create_notification(template=template)

    complaint = Complaint(notification_id=notification.id,
                          service_id=service.id,
                          ses_feedback_id=str(uuid.uuid4()),
                          complaint_type='abuse',
                          complaint_date=datetime.utcnow(),
                          created_at=created_at if created_at else datetime.now()
                          )
    db.session.add(complaint)
    db.session.commit()
    return complaint


def ses_complaint_callback_malformed_message_id():
    return {
        'Signature': 'bb',
        'SignatureVersion': '1', 'MessageAttributes': {}, 'MessageId': '98c6e927-af5d-5f3b-9522-bab736f2cbde',
        'UnsubscribeUrl': 'https://sns.eu-west-1.amazonaws.com',
        'TopicArn': 'arn:ses_notifications', 'Type': 'Notification',
        'Timestamp': '2018-06-05T14:00:15.952Z', 'Subject': None,
        'Message': '{"notificationType":"Complaint","complaint":{"complainedRecipients":[{"emailAddress":"recipient1@example.com"}],"timestamp":"2018-06-05T13:59:58.000Z","feedbackId":"ses_feedback_id"},"mail":{"timestamp":"2018-06-05T14:00:15.950Z","source":"\\"Some Service\\" <someservicenotifications.service.gov.uk>","sourceArn":"arn:identity/notifications.service.gov.uk","sourceIp":"52.208.24.161","sendingAccountId":"888450439860","badMessageId":"ref1","destination":["recipient1@example.com"]}}',  # noqa
        'SigningCertUrl': 'https://sns.pem'
    }


def ses_complaint_callback_with_missing_complaint_type():
    """
    https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html#complaint-object
    """
    return {
        'Signature': 'bb',
        'SignatureVersion': '1', 'MessageAttributes': {}, 'MessageId': '98c6e927-af5d-5f3b-9522-bab736f2cbde',
        'UnsubscribeUrl': 'https://sns.eu-west-1.amazonaws.com',
        'TopicArn': 'arn:ses_notifications', 'Type': 'Notification',
        'Timestamp': '2018-06-05T14:00:15.952Z', 'Subject': None,
        'Message': '{"notificationType":"Complaint","complaint":{"complainedRecipients":[{"emailAddress":"recipient1@example.com"}],"timestamp":"2018-06-05T13:59:58.000Z","feedbackId":"ses_feedback_id"},"mail":{"timestamp":"2018-06-05T14:00:15.950Z","source":"\\"Some Service\\" <someservicenotifications.service.gov.uk>","sourceArn":"arn:identity/notifications.service.gov.uk","sourceIp":"52.208.24.161","sendingAccountId":"888450439860","messageId":"ref1","destination":["recipient1@example.com"]}}',  # noqa
        'SigningCertUrl': 'https://sns.pem'
    }


def ses_complaint_callback():
    """
    https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html#complaint-object
    """
    return {
        'Signature': 'bb',
        'SignatureVersion': '1', 'MessageAttributes': {}, 'MessageId': '98c6e927-af5d-5f3b-9522-bab736f2cbde',
        'UnsubscribeUrl': 'https://sns.eu-west-1.amazonaws.com',
        'TopicArn': 'arn:ses_notifications', 'Type': 'Notification',
        'Timestamp': '2018-06-05T14:00:15.952Z', 'Subject': None,
        'Message': '{"notificationType":"Complaint","complaint":{"complaintFeedbackType": "abuse", "complainedRecipients":[{"emailAddress":"recipient1@example.com"}],"timestamp":"2018-06-05T13:59:58.000Z","feedbackId":"ses_feedback_id"},"mail":{"timestamp":"2018-06-05T14:00:15.950Z","source":"\\"Some Service\\" <someservicenotifications.service.gov.uk>","sourceArn":"arn:identity/notifications.service.gov.uk","sourceIp":"52.208.24.161","sendingAccountId":"888450439860","messageId":"ref1","destination":["recipient1@example.com"]}}',  # noqa
        'SigningCertUrl': 'https://sns.pem'
    }


def ses_notification_callback():
    return '{\n  "Type" : "Notification",\n  "MessageId" : "ref1",' \
           '\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",' \
           '\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",' \
           '\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",' \
           '\\"source\\":\\"test@test-domain.com\\",' \
           '\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",' \
           '\\"sendingAccountId\\":\\"123456789012\\",' \
           '\\"messageId\\":\\"ref1\\",' \
           '\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},' \
           '\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",' \
           '\\"processingTimeMillis\\":658,' \
           '\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],' \
           '\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",' \
           '\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",' \
           '\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",' \
           '\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUt' \
           'OowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYL' \
           'VSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMA' \
           'PmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",' \
           '\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750' \
           'dd426d95ee9390147a5624348ee.pem",' \
           '\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&S' \
           'subscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'


def create_service_data_retention(
        service_id,
        notification_type='sms',
        days_of_retention=3
):
    data_retention = insert_service_data_retention(
        service_id=service_id,
        notification_type=notification_type,
        days_of_retention=days_of_retention
    )
    return data_retention
