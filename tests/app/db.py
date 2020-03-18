import random
import uuid
from datetime import datetime, date, timedelta

from app import db
from app.dao.email_branding_dao import dao_create_email_branding
from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.dao.invited_org_user_dao import save_invited_org_user
from app.dao.invited_user_dao import save_invited_user
from app.dao.jobs_dao import dao_create_job
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_created_scheduled_notification
)
from app.dao.organisation_dao import dao_create_organisation, dao_add_service_to_organisation
from app.dao.permissions_dao import permission_dao
from app.dao.service_callback_api_dao import save_service_callback_api
from app.dao.service_data_retention_dao import insert_service_data_retention
from app.dao.service_inbound_api_dao import save_service_inbound_api
from app.dao.service_permissions_dao import dao_add_service_permission
from app.dao.service_sms_sender_dao import update_existing_sms_sender_with_inbound_number, dao_update_service_sms_sender
from app.dao.services_dao import dao_create_service, dao_add_user_to_service
from app.dao.templates_dao import dao_create_template, dao_update_template
from app.dao.users_dao import save_model_user
from app.models import (
    ApiKey,
    DailySortedLetter,
    InboundSms,
    InboundNumber,
    Job,
    Notification,
    EmailBranding,
    LetterRate,
    Organisation,
    Permission,
    Rate,
    Service,
    ServiceEmailReplyTo,
    ServiceInboundApi,
    ServiceCallbackApi,
    ServiceLetterContact,
    ScheduledNotification,
    ServicePermission,
    ServiceSmsSender,
    ServiceWhitelist,
    Template,
    User,
    EMAIL_TYPE,
    MOBILE_TYPE,
    SMS_TYPE,
    LETTER_TYPE,
    KEY_TYPE_NORMAL,
    AnnualBilling,
    InvitedOrganisationUser,
    FactBilling,
    FactNotificationStatus,
    Complaint,
    InvitedUser,
    TemplateFolder,
    LetterBranding,
    Domain,
    NotificationHistory,
    ReturnedLetter,
    ServiceContactList
)


def create_user(
    mobile_number="+447700900986",
    email="notify@digital.cabinet-office.gov.uk",
    state='active',
    id_=None,
    name="Test User"
):
    data = {
        'id': id_ or uuid.uuid4(),
        'name': name,
        'email_address': email,
        'password': 'password',
        'mobile_number': mobile_number,
        'state': state
    }
    user = User.query.filter_by(email_address=email).first()
    if not user:
        user = User(**data)
    save_model_user(user, validated_email_access=True)
    return user


def create_permissions(user, service, *permissions):
    permissions = [
        Permission(service_id=service.id, user_id=user.id, permission=p)
        for p in permissions
    ]

    permission_dao.set_user_service_permission(user, service, permissions, _commit=True)


def create_service(
        user=None,
        service_name="Sample service",
        service_id=None,
        restricted=False,
        count_as_live=True,
        service_permissions=[EMAIL_TYPE, SMS_TYPE],
        research_mode=False,
        active=True,
        email_from=None,
        prefix_sms=True,
        message_limit=1000,
        organisation_type='central',
        check_if_service_exists=False,
        go_live_user=None,
        go_live_at=None,
        crown=True,
        organisation=None
):
    if check_if_service_exists:
        service = Service.query.filter_by(name=service_name).first()
    if (not check_if_service_exists) or (check_if_service_exists and not service):
        service = Service(
            name=service_name,
            message_limit=message_limit,
            restricted=restricted,
            email_from=email_from if email_from else service_name.lower().replace(' ', '.'),
            created_by=user if user else create_user(email='{}@digital.cabinet-office.gov.uk'.format(uuid.uuid4())),
            prefix_sms=prefix_sms,
            organisation_type=organisation_type,
            go_live_user=go_live_user,
            go_live_at=go_live_at,
            crown=crown
        )
        dao_create_service(service, service.created_by, service_id, service_permissions=service_permissions)

        service.active = active
        service.research_mode = research_mode
        service.count_as_live = count_as_live
    else:
        if user and user not in service.users:
            dao_add_user_to_service(service, user)

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
        hidden=False,
        archived=False,
        folder=None,
        postage=None,
        process_type='normal',
):
    data = {
        'name': template_name or '{} Template Name'.format(template_type),
        'template_type': template_type,
        'content': content,
        'service': service,
        'created_by': service.created_by,
        'reply_to': reply_to,
        'hidden': hidden,
        'folder': folder,
        'process_type': process_type
    }
    if template_type == LETTER_TYPE:
        data["postage"] = postage or "second"
    if template_type != SMS_TYPE:
        data['subject'] = subject
    template = Template(**data)
    dao_create_template(template)

    if archived:
        template.archived = archived
        dao_update_template(template)

    return template


def create_notification(
        template=None,
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
        reply_to_text=None,
        created_by_id=None,
        postage=None,
        document_download_count=None,
):
    assert job or template
    if job:
        template = job.template

    if created_at is None:
        created_at = datetime.utcnow()

    if to_field is None:
        to_field = '+447700900855' if template.template_type == SMS_TYPE else 'test@example.com'

    if status != 'created':
        sent_at = sent_at or datetime.utcnow()
        updated_at = updated_at or datetime.utcnow()

    if not one_off and (job is None and api_key is None):
        # we did not specify in test - lets create it
        api_key = ApiKey.query.filter(ApiKey.service == template.service, ApiKey.key_type == key_type).first()
        if not api_key:
            api_key = create_api_key(template.service, key_type=key_type)

    if template.template_type == 'letter' and postage is None:
        postage = 'second'

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
        'created_by_id': created_by_id,
        'postage': postage,
        'document_download_count': document_download_count,
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


def create_notification_history(
        template=None,
        job=None,
        job_row_number=None,
        status='created',
        reference=None,
        created_at=None,
        sent_at=None,
        updated_at=None,
        billable_units=1,
        api_key=None,
        key_type=KEY_TYPE_NORMAL,
        sent_by=None,
        client_reference=None,
        rate_multiplier=None,
        international=False,
        phone_prefix=None,
        created_by_id=None,
        postage=None,
        id=None
):
    assert job or template
    if job:
        template = job.template

    if created_at is None:
        created_at = datetime.utcnow()

    if status != 'created':
        sent_at = sent_at or datetime.utcnow()
        updated_at = updated_at or datetime.utcnow()

    if template.template_type == 'letter' and postage is None:
        postage = 'second'

    data = {
        'id': id or uuid.uuid4(),
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
        'created_by_id': created_by_id,
        'postage': postage
    }
    notification_history = NotificationHistory(**data)
    db.session.add(notification_history)
    db.session.commit()

    return notification_history


def create_job(
        template,
        notification_count=1,
        created_at=None,
        job_status='pending',
        scheduled_for=None,
        processing_started=None,
        processing_finished=None,
        original_file_name='some.csv',
        archived=False,
        contact_list_id=None,
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
        'processing_started': processing_started,
        'processing_finished': processing_finished,
        'archived': archived,
        'contact_list_id': contact_list_id,
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
    if not service.inbound_number:
        create_inbound_number(
            # create random inbound number
            notify_number or '07{:09}'.format(random.randint(0, 1e9 - 1)),
            provider=provider,
            service_id=service.id
        )

    inbound = InboundSms(
        service=service,
        created_at=created_at or datetime.utcnow(),
        notify_number=service.get_inbound_number(),
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


def create_letter_rate(start_date=None, end_date=None, crown=True, sheet_count=1, rate=0.33, post_class='second'):
    if start_date is None:
        start_date = datetime(2016, 1, 1)
    rate = LetterRate(
        id=uuid.uuid4(),
        start_date=start_date,
        end_date=end_date,
        crown=crown,
        sheet_count=sheet_count,
        rate=rate,
        post_class=post_class
    )
    db.session.add(rate)
    db.session.commit()
    return rate


def create_api_key(service, key_type=KEY_TYPE_NORMAL, key_name=None):
    id_ = uuid.uuid4()

    name = key_name if key_name else '{} api key {}'.format(key_type, id_)

    api_key = ApiKey(
        service=service,
        name=name,
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


def create_domain(domain, organisation_id):

    domain = Domain(domain=domain, organisation_id=organisation_id)

    db.session.add(domain)
    db.session.commit()

    return domain


def create_organisation(name='test_org_1', active=True, organisation_type=None, domains=None):
    data = {
        'name': name,
        'active': active,
        'organisation_type': organisation_type,
    }
    organisation = Organisation(**data)
    dao_create_organisation(organisation)

    for domain in domains or []:
        create_domain(domain, organisation.id)

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
                      template,
                      *,
                      provider='test',
                      rate_multiplier=1,
                      international=False,
                      rate=0,
                      billable_unit=1,
                      notifications_sent=1,
                      postage='none'
                      ):
    data = FactBilling(bst_date=bst_date,
                       service_id=template.service_id,
                       template_id=template.id,
                       notification_type=template.template_type,
                       provider=provider,
                       rate_multiplier=rate_multiplier,
                       international=international,
                       rate=rate,
                       billable_units=billable_unit,
                       notifications_sent=notifications_sent,
                       postage=postage)
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
    if job:
        template = job.template
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


def create_service_whitelist(service, email_address=None, mobile_number=None):
    if email_address:
        whitelisted_user = ServiceWhitelist.from_string(service.id, EMAIL_TYPE, email_address)
    elif mobile_number:
        whitelisted_user = ServiceWhitelist.from_string(service.id, MOBILE_TYPE, mobile_number)
    else:
        whitelisted_user = ServiceWhitelist.from_string(service.id, EMAIL_TYPE, 'whitelisted_user@digital.gov.uk')

    db.session.add(whitelisted_user)
    db.session.commit()
    return whitelisted_user


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
        service,
        notification_type='sms',
        days_of_retention=3
):
    data_retention = insert_service_data_retention(
        service_id=service.id,
        notification_type=notification_type,
        days_of_retention=days_of_retention
    )
    return data_retention


def create_invited_user(service=None,
                        to_email_address=None):

    if service is None:
        service = create_service()
    if to_email_address is None:
        to_email_address = 'invited_user@digital.gov.uk'

    from_user = service.users[0]

    data = {
        'service': service,
        'email_address': to_email_address,
        'from_user': from_user,
        'permissions': 'send_messages,manage_service,manage_api_keys',
        'folder_permissions': [str(uuid.uuid4()), str(uuid.uuid4())]
    }
    invited_user = InvitedUser(**data)
    save_invited_user(invited_user)
    return invited_user


def create_template_folder(service, name='foo', parent=None):
    tf = TemplateFolder(name=name, service=service, parent=parent)
    db.session.add(tf)
    db.session.commit()
    return tf


def create_letter_branding(name='HM Government', filename='hm-government'):
    test_domain_branding = LetterBranding(name=name,
                                          filename=filename,
                                          )
    db.session.add(test_domain_branding)
    db.session.commit()
    return test_domain_branding


def set_up_usage_data(start_date):
    year = int(start_date.strftime('%Y'))
    one_week_earlier = start_date - timedelta(days=7)
    two_days_later = start_date + timedelta(days=2)
    one_week_later = start_date + timedelta(days=7)
    one_month_later = start_date + timedelta(days=31)

    service = create_service(service_name='a - with sms and letter')
    letter_template_1 = create_template(service=service, template_type='letter')
    sms_template_1 = create_template(service=service, template_type='sms')
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=10, financial_year_start=year)
    org = create_organisation(name="Org for {}".format(service.name))
    dao_add_service_to_organisation(service=service, organisation_id=org.id)

    service_2 = create_service(service_name='b - emails')
    email_template = create_template(service=service_2, template_type='email')
    org_2 = create_organisation(name='Org for {}'.format(service_2.name))
    dao_add_service_to_organisation(service=service_2, organisation_id=org_2.id)

    service_3 = create_service(service_name='c - letters only')
    letter_template_3 = create_template(service=service_3, template_type='letter')
    org_3 = create_organisation(name="Org for {}".format(service_3.name))
    dao_add_service_to_organisation(service=service_3, organisation_id=org_3.id)

    service_4 = create_service(service_name='d - service without org')
    letter_template_4 = create_template(service=service_4, template_type='letter')

    service_sms_only = create_service(service_name='b - chargeable sms')
    sms_template = create_template(service=service_sms_only, template_type='sms')
    create_annual_billing(service_id=service_sms_only.id, free_sms_fragment_limit=10, financial_year_start=year)

    create_ft_billing(bst_date=one_week_earlier, template=sms_template_1, billable_unit=2, rate=0.11)
    create_ft_billing(bst_date=start_date, template=sms_template_1, billable_unit=2, rate=0.11)
    create_ft_billing(bst_date=two_days_later, template=sms_template_1, billable_unit=1, rate=0.11)
    create_ft_billing(bst_date=one_week_later, template=letter_template_1,
                      notifications_sent=2, billable_unit=1, rate=.35, postage='first')
    create_ft_billing(bst_date=one_month_later, template=letter_template_1,
                      notifications_sent=4, billable_unit=2, rate=.45, postage='second')
    create_ft_billing(bst_date=one_week_later, template=letter_template_1,
                      notifications_sent=2, billable_unit=2, rate=.45, postage='second')

    create_ft_billing(bst_date=one_week_earlier, template=sms_template, rate=0.11, billable_unit=12)
    create_ft_billing(bst_date=two_days_later, template=sms_template, rate=0.11)
    create_ft_billing(bst_date=one_week_later, template=sms_template, billable_unit=2, rate=0.11)

    create_ft_billing(bst_date=start_date, template=letter_template_3,
                      notifications_sent=2, billable_unit=3, rate=.50, postage='first')
    create_ft_billing(bst_date=one_week_later, template=letter_template_3,
                      notifications_sent=8, billable_unit=5, rate=.65, postage='second')
    create_ft_billing(bst_date=one_month_later, template=letter_template_3,
                      notifications_sent=12, billable_unit=5, rate=.65, postage='second')

    create_ft_billing(bst_date=two_days_later, template=letter_template_4,
                      notifications_sent=15, billable_unit=4, rate=.55, postage='second')

    create_ft_billing(bst_date=start_date, template=email_template, notifications_sent=10)

    return org, org_3, service, service_3, service_4, service_sms_only, org_2, service_2


def create_returned_letter(service=None, reported_at=None, notification_id=None):
    if not service:
        service = create_service(service_name='a - with sms and letter')
    returned_letter = ReturnedLetter(
        service_id=service.id,
        reported_at=reported_at or datetime.utcnow(),
        notification_id=notification_id or uuid.uuid4(),
        created_at=datetime.utcnow(),
    )

    db.session.add(returned_letter)
    db.session.commit()
    return returned_letter


def create_service_contact_list(
    service=None,
    original_file_name='EmergencyContactList.xls',
    row_count=100,
    template_type='email',
    created_by_id=None
):
    if not service:
        service = create_service(service_name='service for contact list', user=create_user())

    contact_list = ServiceContactList(
        service_id=service.id,
        original_file_name=original_file_name,
        row_count=row_count,
        template_type=template_type,
        created_by_id=created_by_id or service.users[0].id,
        created_at=datetime.utcnow(),
    )
    db.session.add(contact_list)
    db.session.commit()
    return contact_list
