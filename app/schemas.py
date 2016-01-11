from . import ma
from . import models
from marshmallow import post_load

# TODO I think marshmallow provides a better integration and error handling.
# Would be better to replace functionality in dao with the marshmallow supported
# functionality.
# http://marshmallow.readthedocs.org/en/latest/api_reference.html


class UserSchema(ma.ModelSchema):
    class Meta:
        model = models.User
        exclude = ("updated_at", "created_at", "user_to_service")

    def make_object(self, data):
        # TODO possibly override to handle instance creation
        return super(UserSchema, self).make_object(data)

    # def dump(self, obj, many=None, update_fields=True, **kwargs):
    #     retval = super(UserSchema, self).dump(
    #         obj, many=many, update_fields=update_fields, **kwargs)
    #     if not many and 'email_address' not in retval.data:
    #         retval.data['email_address'] = obj.email_address
    #     return retval


# TODO process users list, to return a list of user.id
# Should that list be restricted by the auth parsed??
class ServiceSchema(ma.ModelSchema):
    class Meta:
        model = models.Service
        exclude = ("updated_at", "created_at")

    def make_object(self, data):
        # TODO possibly override to handle instance creation
        return super(ServiceSchema, self).make_object(data)


user_schema = UserSchema()
users_schema = UserSchema(many=True)
service_schema = ServiceSchema()
services_schema = ServiceSchema(many=True)
