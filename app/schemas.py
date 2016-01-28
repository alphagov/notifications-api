from . import ma
from . import models
from marshmallow import post_load

# TODO I think marshmallow provides a better integration and error handling.
# Would be better to replace functionality in dao with the marshmallow supported
# functionality.
# http://marshmallow.readthedocs.org/en/latest/api_reference.html


class UserSchema(ma.ModelSchema):

    def __init__(self, *args, load_json=False, **kwargs):
        self.load_json = load_json
        super(UserSchema, self).__init__(*args, **kwargs)

    class Meta:
        model = models.User
        exclude = (
            "updated_at", "created_at", "user_to_service",
            "_password", "verify_codes")

    @post_load
    def make_instance(self, data):
        """Deserialize data to an instance of the model. Update an existing row
        if specified in `self.instance` or loaded by primary key(s) in the data;
        else create a new row.
        :param data: Data to deserialize.
        """
        if self.load_json:
            return data
        return super(UserSchema, self).make_instance(data)


# TODO process users list, to return a list of user.id
# Should that list be restricted by the auth parsed??
class ServiceSchema(ma.ModelSchema):
    class Meta:
        model = models.Service
        exclude = ("updated_at", "created_at", "api_keys", "templates", "jobs")


class TemplateSchema(ma.ModelSchema):
    class Meta:
        model = models.Template
        exclude = ("updated_at", "created_at", "service_id", "jobs")


class ApiKeySchema(ma.ModelSchema):
    class Meta:
        model = models.ApiKey
        exclude = ("service", "secret")


class JobSchema(ma.ModelSchema):
    class Meta:
        model = models.Job


class VerifyCodeSchema(ma.ModelSchema):
    class Meta:
        model = models.VerifyCode
        exclude = ('user', "_code", "expiry_datetime", "code_used", "created_at")


user_schema = UserSchema()
user_schema_load_json = UserSchema(load_json=True)
users_schema = UserSchema(many=True)
service_schema = ServiceSchema()
services_schema = ServiceSchema(many=True)
template_schema = TemplateSchema()
templates_schema = TemplateSchema(many=True)
api_key_schema = ApiKeySchema()
api_keys_schema = ApiKeySchema(many=True)
job_schema = JobSchema()
jobs_schema = JobSchema(many=True)
verify_code_schema = VerifyCodeSchema()
