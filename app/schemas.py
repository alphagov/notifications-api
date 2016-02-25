import re
from flask import current_app
from flask_marshmallow.fields import fields
from . import ma
from . import models
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


user_schema = UserSchema()
user_schema_load_json = UserSchema(load_json=True)
users_schema = UserSchema(many=True)
service_schema = ServiceSchema()
service_schema_load_json = ServiceSchema(load_json=True)
services_schema = ServiceSchema(many=True)
template_schema = TemplateSchema()
template_schema_load_json = TemplateSchema(load_json=True)
templates_schema = TemplateSchema(many=True)
api_key_schema = ApiKeySchema()
api_key_schema_load_json = ApiKeySchema(load_json=True)
api_keys_schema = ApiKeySchema(many=True)
job_schema = JobSchema()
job_schema_load_json = JobSchema(load_json=True)
jobs_schema = JobSchema(many=True)
old_request_verify_code_schema = OldRequestVerifyCodeSchema()
request_verify_code_schema = RequestVerifyCodeSchema()
sms_admin_notification_schema = SmsAdminNotificationSchema()
sms_template_notification_schema = SmsTemplateNotificationSchema()
job_sms_template_notification_schema = JobSmsTemplateNotificationSchema()
email_notification_schema = EmailNotificationSchema()
job_email_template_notification_schema = JobEmailTemplateNotificationSchema()
notification_status_schema = NotificationStatusSchema()
notifications_status_schema = NotificationStatusSchema(many=True)
notification_status_schema_load_json = NotificationStatusSchema(load_json=True)
