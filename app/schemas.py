import re
from flask import current_app
from flask_marshmallow.fields import fields
from . import ma
from . import models
from app.dao.permissions_dao import permission_dao
from marshmallow import (post_load, ValidationError, validates, validates_schema)

mobile_regex = re.compile("^\\+44[\\d]{10}$")

email_regex = re.compile("(^[^@^\\s]+@[^@^\\.^\\s]+(\\.[^@^\\.^\\s]*)*\.(.+))")


# TODO I think marshmallow provides a better integration and error handling.
# Would be better to replace functionality in dao with the marshmallow supported
# functionality.
# http://marshmallow.readthedocs.org/en/latest/api_reference.html


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

    # Code to envelope the input and response.
    # TOBE added soon.

    # @pre_load(pass_many=True)
    # def unwrap_envelope(self, data, many):
    #     key = self.get_envelope_key(many)
    #     return data[key]

    # @post_dump(pass_many=True)
    # def wrap_with_envelope(self, data, many):
    #     key = self.get_envelope_key(many)
    #     return {key: data}

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


class TemplateSchema(BaseSchema):
    class Meta:
        model = models.Template
        exclude = ("updated_at", "created_at", "service_id", "jobs")


class ApiKeySchema(BaseSchema):
    class Meta:
        model = models.ApiKey
        exclude = ("service", "secret")


class JobSchema(BaseSchema):
    class Meta:
        model = models.Job


# TODO: Remove this schema once the admin app has stopped using the /user/<user_id>code endpoint
class OldRequestVerifyCodeSchema(ma.Schema):

    code_type = fields.Str(required=True)
    to = fields.Str(required=False)

    @validates('code_type')
    def validate_code_type(self, code):
        if code not in models.VERIFY_CODE_TYPES:
            raise ValidationError('Invalid code type')


class RequestVerifyCodeSchema(ma.Schema):
    to = fields.Str(required=False)


class NotificationSchema(ma.Schema):
    personalisation = fields.Dict(required=False)
    pass


class SmsNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)

    @validates('to')
    def validate_to(self, value):
        if not mobile_regex.match(value):
            raise ValidationError('Invalid phone number, must be of format +441234123123')


class EmailNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)
    template = fields.Int(required=True)

    @validates('to')
    def validate_to(self, value):
        if not email_regex.match(value):
            raise ValidationError('Invalid email')


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

    class Meta:
        model = models.Notification


class InvitedUserSchema(BaseSchema):

    class Meta:
        model = models.InvitedUser

    @validates('email_address')
    def validate_to(self, value):
        if not email_regex.match(value):
            raise ValidationError('Invalid email')


class PermissionSchema(BaseSchema):

    __envelope__ = {
        'single': 'permission',
        'many': 'permissions',
    }

    class Meta:
        model = models.Permission
        exclude = ("created_at",)


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
old_request_verify_code_schema = OldRequestVerifyCodeSchema()
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
