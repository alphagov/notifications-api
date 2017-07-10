import re
from datetime import (
    datetime,
    date,
    timedelta)
from flask_marshmallow.fields import fields
from marshmallow import (
    post_load,
    ValidationError,
    validates,
    validates_schema,
    pre_load,
    pre_dump,
    post_dump
)
from marshmallow_sqlalchemy import field_for

from notifications_utils.recipients import (
    validate_email_address,
    InvalidEmailError,
    validate_phone_number,
    InvalidPhoneError,
    validate_and_format_phone_number
)

from app import ma
from app import models
from app.models import ServicePermission
from app.dao.permissions_dao import permission_dao
from app.utils import get_template_instance


def _validate_positive_number(value, msg="Not a positive integer"):
    try:
        page_int = int(value)
        if page_int < 1:
            raise ValidationError(msg)
    except:
        raise ValidationError(msg)


def _validate_datetime_not_more_than_96_hours_in_future(dte, msg="Date cannot be more than 96hrs in the future"):
    if dte > datetime.utcnow() + timedelta(hours=96):
        raise ValidationError(msg)


def _validate_not_in_future(dte, msg="Date cannot be in the future"):
    if dte > date.today():
        raise ValidationError(msg)


def _validate_not_in_past(dte, msg="Date cannot be in the past"):
    if dte < date.today():
        raise ValidationError(msg)


def _validate_datetime_not_in_future(dte, msg="Date cannot be in the future"):
    if dte > datetime.utcnow():
        raise ValidationError(msg)


def _validate_datetime_not_in_past(dte, msg="Date cannot be in the past"):
    if dte < datetime.utcnow():
        raise ValidationError(msg)


class BaseSchema(ma.ModelSchema):

    def __init__(self, load_json=False, *args, **kwargs):
        self.load_json = load_json
        super(BaseSchema, self).__init__(*args, **kwargs)

    @post_load
    def make_instance(self, data):
        """Deserialize data to an instance of the model. Update an existing row
        if specified in `self.instance` or loaded by primary key(s) in the data;
        else create a new row.
        :param data: Data to deserialize.
        """
        if self.load_json:
            return data
        return super(BaseSchema, self).make_instance(data)


class UserSchema(BaseSchema):

    permissions = fields.Method("user_permissions", dump_only=True)
    password_changed_at = field_for(models.User, 'password_changed_at', format='%Y-%m-%d %H:%M:%S.%f')
    created_at = field_for(models.User, 'created_at', format='%Y-%m-%d %H:%M:%S.%f')

    def user_permissions(self, usr):
        retval = {}
        for x in permission_dao.get_permissions_by_user_id(usr.id):
            service_id = str(x.service_id)
            if service_id not in retval:
                retval[service_id] = []
            retval[service_id].append(x.permission)
        return retval

    class Meta:
        model = models.User
        exclude = (
            "updated_at", "created_at", "user_to_service",
            "_password", "verify_codes")
        strict = True


class UserUpdateAttributeSchema(BaseSchema):

    class Meta:
        model = models.User
        exclude = (
            'id', 'updated_at', 'created_at', 'user_to_service',
            '_password', 'verify_codes', 'logged_in_at', 'password_changed_at',
            'failed_login_count', 'state', 'platform_admin')
        strict = True

    @validates('name')
    def validate_name(self, value):
        if not value:
            raise ValidationError('Invalid name')

    @validates('email_address')
    def validate_email_address(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(str(e))

    @validates('mobile_number')
    def validate_mobile_number(self, value):
        try:
            validate_phone_number(value)
        except InvalidPhoneError as error:
            raise ValidationError('Invalid phone number: {}'.format(error))

    @validates_schema(pass_original=True)
    def check_unknown_fields(self, data, original_data):
        for key in original_data:
            if key not in self.fields:
                raise ValidationError('Unknown field name {}'.format(key))


class UserUpdatePasswordSchema(BaseSchema):

    class Meta:
        model = models.User
        only = ('password')
        strict = True

    @validates_schema(pass_original=True)
    def check_unknown_fields(self, data, original_data):
        for key in original_data:
            if key not in self.fields:
                raise ValidationError('Unknown field name {}'.format(key))


class ProviderDetailsSchema(BaseSchema):
    created_by = fields.Nested(UserSchema, only=['id', 'name', 'email_address'], dump_only=True)

    class Meta:
        model = models.ProviderDetails
        exclude = ("provider_rates", "provider_stats")
        strict = True


class ProviderDetailsHistorySchema(BaseSchema):
    created_by = fields.Nested(UserSchema, only=['id', 'name', 'email_address'], dump_only=True)

    class Meta:
        model = models.ProviderDetailsHistory
        exclude = ("provider_rates", "provider_stats")
        strict = True


class ServiceSchema(BaseSchema):

    free_sms_fragment_limit = fields.Method(method_name='get_free_sms_fragment_limit')
    created_by = field_for(models.Service, 'created_by', required=True)
    organisation = field_for(models.Service, 'organisation')
    branding = field_for(models.Service, 'branding')
    dvla_organisation = field_for(models.Service, 'dvla_organisation')
    permissions = fields.Method("service_permissions")
    override_flag = False

    def get_free_sms_fragment_limit(selfs, service):
        return service.free_sms_fragment_limit()

    def service_permissions(self, service):
        return [p.permission for p in service.permissions]

    class Meta:
        model = models.Service
        dump_only = ['free_sms_fragment_limit']
        exclude = (
            'updated_at',
            'created_at',
            'api_keys',
            'templates',
            'jobs',
            'old_id',
            'template_statistics',
            'service_provider_stats',
            'service_notification_stats',
        )
        strict = True

    @validates('sms_sender')
    def validate_sms_sender(self, value):
        if value and not re.match(r'^[a-zA-Z0-9\s]+$', value):
            raise ValidationError('Only alphanumeric characters allowed')

    @validates('permissions')
    def validate_permissions(self, value):
        permissions = [v.permission for v in value]
        for p in permissions:
            if p not in models.SERVICE_PERMISSION_TYPES:
                raise ValidationError("Invalid Service Permission: '{}'".format(p))

        if len(set(permissions)) != len(permissions):
            duplicates = list(set([x for x in permissions if permissions.count(x) > 1]))
            raise ValidationError('Duplicate Service Permission: {}'.format(duplicates))

    @pre_load()
    def format_for_data_model(self, in_data):
        if isinstance(in_data, dict) and 'permissions' in in_data:
            str_permissions = in_data['permissions']
            permissions = []
            for p in str_permissions:
                permission = ServicePermission(service_id=in_data["id"], permission=p)
                permissions.append(permission)

            in_data['permissions'] = permissions


class DetailedServiceSchema(BaseSchema):
    statistics = fields.Dict()

    free_sms_fragment_limit = fields.Method(method_name='get_free_sms_fragment_limit')

    def get_free_sms_fragment_limit(selfs, service):
        return service.free_sms_fragment_limit()

    class Meta:
        model = models.Service
        exclude = (
            'api_keys',
            'templates',
            'users',
            'created_by',
            'jobs',
            'template_statistics',
            'service_provider_stats',
            'service_notification_stats',
            'organisation'
        )


class NotificationModelSchema(BaseSchema):
    class Meta:
        model = models.Notification
        strict = True
        exclude = ('_personalisation', 'job', 'service', 'template', 'api_key', '_status_enum', '_status_fkey')

    status = fields.String(required=False)


class BaseTemplateSchema(BaseSchema):

    class Meta:
        model = models.Template
        exclude = ("service_id", "jobs")
        strict = True


class TemplateSchema(BaseTemplateSchema):

    created_by = field_for(models.Template, 'created_by', required=True)
    process_type = field_for(models.Template, 'process_type')
    redact_personalisation = fields.Method("redact")

    def redact(self, template):
        return template.redact_personalisation

    @validates_schema
    def validate_type(self, data):
        if data.get('template_type') in [models.EMAIL_TYPE, models.LETTER_TYPE]:
            subject = data.get('subject')
            if not subject or subject.strip() == '':
                raise ValidationError('Invalid template subject', 'subject')


class TemplateHistorySchema(BaseSchema):

    created_by = fields.Nested(UserSchema, only=['id', 'name', 'email_address'], dump_only=True)
    created_at = field_for(models.Template, 'created_at', format='%Y-%m-%d %H:%M:%S.%f')

    class Meta:
        model = models.TemplateHistory


class NotificationsStatisticsSchema(BaseSchema):
    class Meta:
        model = models.NotificationStatistics
        strict = True

    @pre_dump
    def handle_date_str(self, in_data):
        if isinstance(in_data, dict) and 'day' in in_data:
            in_data['day'] = datetime.strptime(in_data['day'], '%Y-%m-%d').date()
        return in_data


class ApiKeySchema(BaseSchema):

    created_by = field_for(models.ApiKey, 'created_by', required=True)
    key_type = field_for(models.ApiKey, 'key_type', required=True)

    class Meta:
        model = models.ApiKey
        exclude = ("service", "_secret")
        strict = True


class JobSchema(BaseSchema):
    created_by_user = fields.Nested(UserSchema, attribute="created_by",
                                    dump_to="created_by", only=["id", "name"], dump_only=True)
    created_by = field_for(models.Job, 'created_by', required=True, load_only=True)

    job_status = field_for(models.JobStatus, 'name', required=False)

    scheduled_for = fields.DateTime()
    service_name = fields.Nested(
        ServiceSchema, attribute="service", dump_to="service_name", only=["name"], dump_only=True)

    @validates('scheduled_for')
    def validate_scheduled_for(self, value):
        _validate_datetime_not_in_past(value)
        _validate_datetime_not_more_than_96_hours_in_future(value)

    class Meta:
        model = models.Job
        exclude = (
            'notifications',
            'notifications_sent',
            'notifications_delivered',
            'notifications_failed')
        strict = True


class RequestVerifyCodeSchema(ma.Schema):

    class Meta:
        strict = True

    to = fields.Str(required=False)


class NotificationSchema(ma.Schema):

    class Meta:
        strict = True

    status = fields.String(required=False)
    personalisation = fields.Dict(required=False)


class SmsNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)

    @validates('to')
    def validate_to(self, value):
        try:
            validate_phone_number(value, international=True)
        except InvalidPhoneError as error:
            raise ValidationError('Invalid phone number: {}'.format(error))

    @post_load
    def format_phone_number(self, item):
        item['to'] = validate_and_format_phone_number(item['to'], international=True)
        return item


class EmailNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)
    template = fields.Str(required=True)

    @validates('to')
    def validate_to(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(str(e))


class SmsTemplateNotificationSchema(SmsNotificationSchema):
    template = fields.Str(required=True)
    job = fields.String()


class JobSmsTemplateNotificationSchema(SmsNotificationSchema):
    template = fields.Str(required=True)
    job = fields.String(required=True)


class JobEmailTemplateNotificationSchema(EmailNotificationSchema):
    template = fields.Str(required=True)
    job = fields.String(required=True)


class SmsAdminNotificationSchema(SmsNotificationSchema):
    content = fields.Str(required=True)


class NotificationWithTemplateSchema(BaseSchema):
    class Meta:
        model = models.Notification
        strict = True
        exclude = ('_personalisation', '_status_enum', '_status_fkey')

    template = fields.Nested(
        TemplateSchema,
        only=['id', 'version', 'name', 'template_type', 'content', 'subject', 'redact_personalisation'],
        dump_only=True
    )
    job = fields.Nested(JobSchema, only=["id", "original_file_name"], dump_only=True)
    created_by = fields.Nested(UserSchema, only=['id', 'name', 'email_address'], dump_only=True)
    status = fields.String(required=False)
    personalisation = fields.Dict(required=False)
    key_type = field_for(models.Notification, 'key_type', required=True)
    key_name = fields.String()

    @pre_dump
    def add_api_key_name(self, in_data):
        if in_data.api_key:
            in_data.key_name = in_data.api_key.name
        else:
            in_data.key_name = None
        return in_data


class NotificationWithPersonalisationSchema(NotificationWithTemplateSchema):
    template_history = fields.Nested(TemplateHistorySchema,
                                     only=['id', 'name', 'template_type', 'content', 'subject', 'version'],
                                     dump_only=True)

    class Meta(NotificationWithTemplateSchema.Meta):
        # mark as many fields as possible as required since this is a public api.
        # WARNING: Does _not_ reference fields computed in handle_template_merge, such as
        # 'body', 'subject' [for emails], and 'content_char_count'
        fields = (
            # db rows
            'id', 'to', 'job_row_number', 'template_version', 'billable_units', 'notification_type', 'created_at',
            'sent_at', 'sent_by', 'updated_at', 'status', 'reference',
            # computed fields
            'personalisation',
            # relationships
            'service', 'job', 'api_key', 'template_history'
        )

    @pre_dump
    def handle_personalisation_property(self, in_data):
        self.personalisation = in_data.personalisation
        return in_data

    @post_dump
    def handle_template_merge(self, in_data):
        in_data['template'] = in_data.pop('template_history')
        template = get_template_instance(in_data['template'], in_data['personalisation'])
        in_data['body'] = str(template)
        if in_data['template']['template_type'] == models.EMAIL_TYPE:
            in_data['subject'] = template.subject
            in_data['content_char_count'] = None
        else:
            in_data['content_char_count'] = template.content_count

        in_data.pop('personalisation', None)
        in_data['template'].pop('content', None)
        in_data['template'].pop('subject', None)
        return in_data


class InvitedUserSchema(BaseSchema):

    class Meta:
        model = models.InvitedUser
        strict = True

    @validates('email_address')
    def validate_to(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(str(e))


class PermissionSchema(BaseSchema):

    # Override generated fields
    user = field_for(models.Permission, 'user', dump_only=True)
    service = field_for(models.Permission, 'service', dump_only=True)
    permission = field_for(models.Permission, 'permission')

    __envelope__ = {
        'single': 'permission',
        'many': 'permissions',
    }

    class Meta:
        model = models.Permission
        exclude = ("created_at",)
        strict = True


class EmailDataSchema(ma.Schema):

    class Meta:
        strict = True

    email = fields.Str(required=True)

    @validates('email')
    def validate_email(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(str(e))


class NotificationsFilterSchema(ma.Schema):

    class Meta:
        strict = True

    template_type = fields.Nested(BaseTemplateSchema, only=['template_type'], many=True)
    status = fields.Nested(NotificationModelSchema, only=['status'], many=True)
    page = fields.Int(required=False)
    page_size = fields.Int(required=False)
    limit_days = fields.Int(required=False)
    include_jobs = fields.Boolean(required=False)
    include_from_test_key = fields.Boolean(required=False)
    older_than = fields.UUID(required=False)
    format_for_csv = fields.String()
    to = fields.String()

    @pre_load
    def handle_multidict(self, in_data):
        if isinstance(in_data, dict) and hasattr(in_data, 'getlist'):
            out_data = dict([(k, in_data.get(k)) for k in in_data.keys()])
            if 'template_type' in in_data:
                out_data['template_type'] = [{'template_type': x} for x in in_data.getlist('template_type')]
            if 'status' in in_data:
                out_data['status'] = [{"status": x} for x in in_data.getlist('status')]

        return out_data

    @post_load
    def convert_schema_object_to_field(self, in_data):
        if 'template_type' in in_data:
            in_data['template_type'] = [x.template_type for x in in_data['template_type']]
        if 'status' in in_data:
            in_data['status'] = [x.status for x in in_data['status']]
        return in_data

    @validates('page')
    def validate_page(self, value):
        _validate_positive_number(value)

    @validates('page_size')
    def validate_page_size(self, value):
        _validate_positive_number(value)


class ServiceHistorySchema(ma.Schema):
    id = fields.UUID()
    name = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()
    active = fields.Boolean()
    message_limit = fields.Integer()
    restricted = fields.Boolean()
    email_from = fields.String()
    created_by_id = fields.UUID()
    version = fields.Integer()


class ApiKeyHistorySchema(ma.Schema):
    id = fields.UUID()
    name = fields.String()
    service_id = fields.UUID()
    expiry_date = fields.DateTime()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()
    created_by_id = fields.UUID()


class EventSchema(BaseSchema):
    class Meta:
        model = models.Event
        strict = True


class OrganisationSchema(BaseSchema):
    class Meta:
        model = models.Organisation
        strict = True


class DaySchema(ma.Schema):

    class Meta:
        strict = True

    day = fields.Date(required=True)

    @validates('day')
    def validate_day(self, value):
        _validate_not_in_future(value)


class UnarchivedTemplateSchema(BaseSchema):
    archived = fields.Boolean(required=True)

    @validates_schema
    def validate_archived(self, data):
        if data['archived']:
            raise ValidationError('Template has been deleted', 'template')


user_schema = UserSchema()
user_schema_load_json = UserSchema(load_json=True)
user_update_schema_load_json = UserUpdateAttributeSchema(load_json=True, partial=True)
user_update_password_schema_load_json = UserUpdatePasswordSchema(load_json=True, partial=True)
service_schema = ServiceSchema()
service_schema_load_json = ServiceSchema(load_json=True)
detailed_service_schema = DetailedServiceSchema()
template_schema = TemplateSchema()
template_schema_load_json = TemplateSchema(load_json=True)
api_key_schema = ApiKeySchema()
api_key_schema_load_json = ApiKeySchema(load_json=True)
job_schema = JobSchema()
job_schema_load_json = JobSchema(load_json=True)
request_verify_code_schema = RequestVerifyCodeSchema()
sms_admin_notification_schema = SmsAdminNotificationSchema()
sms_template_notification_schema = SmsTemplateNotificationSchema()
job_sms_template_notification_schema = JobSmsTemplateNotificationSchema()
email_notification_schema = EmailNotificationSchema()
job_email_template_notification_schema = JobEmailTemplateNotificationSchema()
notification_schema = NotificationModelSchema()
notification_with_template_schema = NotificationWithTemplateSchema()
notification_with_personalisation_schema = NotificationWithPersonalisationSchema()
invited_user_schema = InvitedUserSchema()
permission_schema = PermissionSchema()
email_data_request_schema = EmailDataSchema()
notifications_statistics_schema = NotificationsStatisticsSchema()
notifications_filter_schema = NotificationsFilterSchema()
service_history_schema = ServiceHistorySchema()
api_key_history_schema = ApiKeyHistorySchema()
template_history_schema = TemplateHistorySchema()
event_schema = EventSchema()
organisation_schema = OrganisationSchema()
provider_details_schema = ProviderDetailsSchema()
provider_details_history_schema = ProviderDetailsHistorySchema()
day_schema = DaySchema()
unarchived_template_schema = UnarchivedTemplateSchema()
