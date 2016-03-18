from flask_marshmallow.fields import fields
from . import ma
from . import models
from app.dao.permissions_dao import permission_dao
from marshmallow import (post_load, ValidationError, validates, validates_schema)
from marshmallow_sqlalchemy import field_for
from utils.recipients import (
    validate_email_address, InvalidEmailError,
    validate_phone_number, InvalidPhoneError,
    format_phone_number
)


# TODO I think marshmallow provides a better integration and error handling.
# Would be better to replace functionality in dao with the marshmallow supported
# functionality.
# http://marshmallow.readthedocs.org/en/latest/api_reference.html
# http://marshmallow.readthedocs.org/en/latest/extending.html


class BaseSchema(ma.ModelSchema):
    def __init__(self, *args, load_json=False, **kwargs):
        self.load_json = load_json
        super(BaseSchema, self).__init__(*args, **kwargs)

    __envelope__ = {
        'single': None,
        'many': None
    }

    def get_envelope_key(self, many):
        """Helper to get the envelope key."""
        key = self.__envelope__['many'] if many else self.__envelope__['single']
        assert key is not None, "Envelope key undefined"
        return key

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
        for x in permission_dao.get_query({'user': usr.id}):
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


class ServiceSchema(BaseSchema):
    class Meta:
        model = models.Service
        exclude = ("updated_at", "created_at", "api_keys", "templates", "jobs", 'old_id')

    @validates_schema
    def validate_all(self, data):
        # There are 2 instances where we want to check
        # for duplicate service name. One when they updating
        # an existing service and when they are creating a service
        name = data.get('name', None)
        service = models.Service.query.filter_by(name=name).first()
        error_msg = "Duplicate service name '{}'".format(name)
        if 'id' in data:
            if service and str(service.id) != data['id']:
                raise ValidationError(error_msg, 'name')
        else:
            if service:
                raise ValidationError(error_msg, 'name')


class TemplateSchema(BaseSchema):
    class Meta:
        model = models.Template
        exclude = ("updated_at", "created_at", "service_id", "jobs")


class NotificationsStatisticsSchema(BaseSchema):
    class Meta:
        model = models.NotificationStatistics


class ApiKeySchema(BaseSchema):
    class Meta:
        model = models.ApiKey
        exclude = ("service", "secret")


class JobSchema(BaseSchema):
    class Meta:
        model = models.Job


class RequestVerifyCodeSchema(ma.Schema):
    to = fields.Str(required=False)


class NotificationSchema(ma.Schema):
    personalisation = fields.Dict(required=False)
    pass


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
        item['to'] = format_phone_number(validate_phone_number(
            item['to'])
        )
        return item


class EmailNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)
    template = fields.Int(required=True)

    @validates('to')
    def validate_to(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(e.message)


class SmsTemplateNotificationSchema(SmsNotificationSchema):
    template = fields.Int(required=True)
    job = fields.String()


class JobSmsTemplateNotificationSchema(SmsNotificationSchema):
    template = fields.Int(required=True)
    job = fields.String(required=True)


class JobEmailTemplateNotificationSchema(EmailNotificationSchema):
    template = fields.Int(required=True)
    job = fields.String(required=True)


class SmsAdminNotificationSchema(SmsNotificationSchema):
    content = fields.Str(required=True)


class NotificationStatusSchema(BaseSchema):

    template = fields.Nested(TemplateSchema, only=["id", "name", "template_type"], dump_only=True)
    job = fields.Nested(JobSchema, only=["id", "original_file_name"], dump_only=True)

    class Meta:
        model = models.Notification


class InvitedUserSchema(BaseSchema):

    class Meta:
        model = models.InvitedUser

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


class EmailDataSchema(ma.Schema):
    email = fields.Str(required=False)

    @validates('email')
    def validate_email(self, value):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            raise ValidationError(e.message)

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
