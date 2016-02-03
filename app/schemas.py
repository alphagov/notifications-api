import re
from flask_marshmallow.fields import fields
from . import ma
from . import models
from marshmallow_sqlalchemy.fields import Related
from marshmallow import (post_load, ValidationError, validates, validates_schema)

mobile_regex = re.compile("^\\+44[\\d]{10}$")


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


class RequestVerifyCodeSchema(ma.Schema):

    code_type = fields.Str(required=True)
    to = fields.Str(required=False)

    @validates('code_type')
    def validate_code_type(self, code):
        if code not in models.VERIFY_CODE_TYPES:
            raise ValidationError('Invalid code type')


# TODO main purpose to be added later
# when processing templates, template will be
# common for all notifications.
class NotificationSchema(ma.Schema):
    pass


class SmsNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)

    @validates('to')
    def validate_to(self, value):
        if not mobile_regex.match(value):
            raise ValidationError('Invalid phone number, must be of format +441234123123')


class SmsTemplateNotificationSchema(SmsNotificationSchema):
    template = fields.Int(required=True)

    @validates('template')
    def validate_template(self, value):
        if not models.Template.query.filter_by(id=value).first():
            # TODO is this message consistent with what marshmallow
            # would normally produce.
            raise ValidationError('Template not found')

    @validates_schema
    def validate_schema(self, data):
        """
        Validate the to field is valid for this template
        """
        template_id = data.get('template', None)
        template = models.Template.query.filter_by(id=template_id).first()
        if template:
            service = template.service
            if service.restricted:
                valid = False
                for usr in service.users:
                    if data['to'] == usr.mobile_number:
                        valid = True
                        break
                if not valid:
                    raise ValidationError('Invalid phone number for restricted service', 'restricted')


class SmsAdminNotificationSchema(SmsNotificationSchema):
    content = fields.Str(required=True)


class EmailNotificationSchema(NotificationSchema):
    to_address = fields.Str(load_from="to", dump_to='to', required=True)
    from_address = fields.Str(load_from="from", dump_to='from', required=True)
    subject = fields.Str(required=True)
    body = fields.Str(load_from="message", dump_to='message', required=True)


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
request_verify_code_schema = RequestVerifyCodeSchema()
sms_admin_notification_schema = SmsAdminNotificationSchema()
sms_template_notification_schema = SmsTemplateNotificationSchema()
email_notification_schema = EmailNotificationSchema()
