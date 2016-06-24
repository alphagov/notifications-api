from datetime import (
    datetime,
    date
)
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
from app.dao.permissions_dao import permission_dao


def _validate_positive_number(value, msg="Not a positive integer"):
    try:
        page_int = int(value)
        if page_int < 1:
            raise ValidationError(msg)
    except:
        raise ValidationError(msg)


def _validate_not_in_future(dte, msg="Date cannot be in the future"):
    if dte > date.today():
        raise ValidationError(msg)


# TODO I think marshmallow provides a better integration and error handling.
# Would be better to replace functionality in dao with the marshmallow supported
# functionality.
# http://marshmallow.readthedocs.org/en/latest/api_reference.html
# http://marshmallow.readthedocs.org/en/latest/extending.html


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


class ProviderDetailsSchema(BaseSchema):
    class Meta:
        model = models.ProviderDetails
        exclude = ("provider_rates", "provider_stats")
        strict = True


class ServiceSchema(BaseSchema):

    created_by = field_for(models.Service, 'created_by', required=True)

    class Meta:
        model = models.Service
        exclude = ("updated_at", "created_at", "api_keys", "templates", "jobs", 'old_id')
        strict = True


class NotificationModelSchema(BaseSchema):
    class Meta:
        model = models.Notification
        strict = True
        exclude = ("_personalisation",)


class BaseTemplateSchema(BaseSchema):

    class Meta:
        model = models.Template
        exclude = ("service_id", "jobs")
        strict = True


class TemplateSchema(BaseTemplateSchema):

    created_by = field_for(models.Template, 'created_by', required=True)

    @validates_schema
    def validate_type(self, data):
        template_type = data.get('template_type')
        if template_type and template_type == 'email':
            subject = data.get('subject')
            if not subject or subject.strip() == '':
                raise ValidationError('Invalid template subject', 'subject')


class TemplateHistorySchema(BaseSchema):

    class Meta:
        # Use the base model class that the history class is created from
        model = models.Template
    # We have to use a method here because the relationship field on the
    # history object is not created.
    created_by = fields.Method("populate_created_by", dump_only=True)
    created_at = field_for(models.Template, 'created_at', format='%Y-%m-%d %H:%M:%S.%f')

    def populate_created_by(self, data):
        usr = models.User.query.filter_by(id=data.created_by_id).one()
        return {'id': str(usr.id), 'name': usr.name, 'email_address': usr.email_address}


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
    key_type = field_for(models.ApiKey, 'key_type', required=True, missing=models.KEY_TYPE_NORMAL)

    class Meta:
        model = models.ApiKey
        exclude = ("service", "secret")
        strict = True


class JobSchema(BaseSchema):
    created_by_user = fields.Nested(UserSchema, attribute="created_by",
                                    dump_to="created_by", only=["id", "name"], dump_only=True)
    created_by = field_for(models.Job, 'created_by', required=True, load_only=True)

    class Meta:
        model = models.Job
        exclude = ('notifications',)
        strict = True


class RequestVerifyCodeSchema(ma.Schema):

    class Meta:
        strict = True

    to = fields.Str(required=False)


class NotificationSchema(ma.Schema):

    class Meta:
        strict = True

    personalisation = fields.Dict(required=False)


class SmsNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)

    @validates('to')
    def validate_to(self, value):
        try:
            validate_phone_number(value)
        except InvalidPhoneError as error:
            raise ValidationError('Invalid phone number: {}'.format(error))

    @post_load
    def format_phone_number(self, item):
        item['to'] = validate_and_format_phone_number(item['to'])
        return item


class EmailNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)
    template = fields.Str(required=True)

    @validates('to')
    def validate_to(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(e.message)


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


class NotificationStatusSchema(BaseSchema):

    template = fields.Nested(TemplateSchema, only=["id", "name", "template_type", "content", "subject"], dump_only=True)
    job = fields.Nested(JobSchema, only=["id", "original_file_name"], dump_only=True)
    personalisation = fields.Dict(required=False)

    class Meta:
        model = models.Notification
        strict = True
        exclude = ('_personalisation',)

    @pre_dump
    def handle_personalisation_property(self, in_data):
        if in_data.personalisation:
            self.personalisation = in_data.personalisation
        return in_data

    @post_dump
    def handle_template_merge(self, in_data):
        if in_data.get('personalisation'):
            from notifications_utils.template import Template
            template = Template(in_data['template'], in_data['personalisation'])
            in_data['body'] = template.replaced
            if in_data['template']['template_type'] == 'email':
                in_data['subject'] = template.replaced_subject
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
            raise ValidationError(e.message)


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

    email = fields.Str(required=False)

    @validates('email')
    def validate_email(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(e.message)


class NotificationsFilterSchema(ma.Schema):

    class Meta:
        strict = True

    template_type = fields.Nested(BaseTemplateSchema, only=['template_type'], many=True)
    status = fields.Nested(NotificationModelSchema, only=['status'], many=True)
    page = fields.Int(required=False)
    page_size = fields.Int(required=False)
    limit_days = fields.Int(required=False)

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


class TemplateStatisticsSchema(BaseSchema):

    template = fields.Nested(TemplateSchema, only=["id",  "name", "template_type"], dump_only=True)

    class Meta:
        model = models.TemplateStatistics
        strict = True


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


class FromToDateSchema(ma.Schema):

    class Meta:
        strict = True

    date_from = fields.Date()
    date_to = fields.Date()

    @validates('date_from')
    def validate_date_from(self, value):
        _validate_not_in_future(value)

    @validates('date_to')
    def validate_date_to(self, value):
        _validate_not_in_future(value)

    @validates_schema
    def validate_dates(self, data):
        df = data.get('date_from')
        dt = data.get('date_to')
        if (df and dt) and (df > dt):
            raise ValidationError("date_from needs to be greater than date_to")


class DaySchema(ma.Schema):

    class Meta:
        strict = True

    day = fields.Date(required=True)

    @validates('day')
    def validate_day(self, value):
        _validate_not_in_future(value)


class WeekAggregateNotificationStatisticsSchema(ma.Schema):

    class Meta:
        strict = True

    date_from = fields.Date()
    week_count = fields.Int()

    @validates('date_from')
    def validate_date_from(self, value):
        _validate_not_in_future(value)

    @validates('week_count')
    def validate_week_count(self, value):
        _validate_positive_number(value)


class UnarchivedTemplateSchema(BaseSchema):
    archived = fields.Boolean(required=True)

    @validates_schema
    def validate_archived(self, data):
        if data['archived']:
            raise ValidationError('Template has been deleted', 'template')


user_schema = UserSchema()
user_schema_load_json = UserSchema(load_json=True)
service_schema = ServiceSchema()
service_schema_load_json = ServiceSchema(load_json=True)
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
notification_status_schema = NotificationStatusSchema()
notification_status_schema_load_json = NotificationStatusSchema(load_json=True)
invited_user_schema = InvitedUserSchema()
permission_schema = PermissionSchema()
email_data_request_schema = EmailDataSchema()
notifications_statistics_schema = NotificationsStatisticsSchema()
notifications_filter_schema = NotificationsFilterSchema()
template_statistics_schema = TemplateStatisticsSchema()
service_history_schema = ServiceHistorySchema()
api_key_history_schema = ApiKeyHistorySchema()
template_history_schema = TemplateHistorySchema()
event_schema = EventSchema()
from_to_date_schema = FromToDateSchema()
provider_details_schema = ProviderDetailsSchema()
week_aggregate_notification_statistics_schema = WeekAggregateNotificationStatisticsSchema()
day_schema = DaySchema()
unarchived_template_schema = UnarchivedTemplateSchema()
