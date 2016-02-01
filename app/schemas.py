from flask_marshmallow.fields import fields
from . import ma
from . import models
from marshmallow import post_load, ValidationError


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
        exclude = ("updated_at", "created_at", "api_keys", "templates", "jobs", "queue_name")


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
    def verify_code_type(self):
        if self not in models.VERIFY_CODE_TYPES:
            raise ValidationError('Invalid code type')

    code_type = fields.Str(required=True, validate=verify_code_type)
    to = fields.Str(required=False)


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
