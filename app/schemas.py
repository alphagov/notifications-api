from marshmallow_sqlalchemy import ModelSchema
from . import models


class UserSchema(ModelSchema):
    class Meta:
        model = models.User


# TODO process users list, to return a list of user.id
# Should that list be restricted??
class ServiceSchema(ModelSchema):
    class Meta:
        model = models.Service


user_schema = ServiceSchema()
users_schema = UserSchema(many=True)
service_schema = ServiceSchema()
services_schema = ServiceSchema(many=True)
