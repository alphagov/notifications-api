import uuid
from datetime import UTC, datetime

from flask import Blueprint, request

from app import db
from app.dao.organisation_dao import (
    dao_add_user_to_organisation,
    dao_get_organisation_by_id,
    dao_remove_user_from_organisation,
)
from app.dao.permissions_dao import permission_dao
from app.dao.services_dao import dao_add_user_to_service
from app.errors import register_errors
from app.functional_tests.testing_schemas import create_functional_test_users_schema
from app.models import Permission, Service, User
from app.schema_validation import validate

test_blueprint = Blueprint("functional_tests", __name__, url_prefix="/__testing/functional")
register_errors(test_blueprint)


@test_blueprint.route("/users", methods=["PUT"])
def create_functional_test_users():
    users_info = request.get_json()
    validate(users_info, create_functional_test_users_schema)

    for user_info in users_info:
        created = False
        if not (user := User.query.filter_by(email_address=user_info["email_address"]).one_or_none()):
            created = True
            user = User()
            user.id = uuid.uuid4()
            user.created_at = datetime.now(UTC).replace(tzinfo=None)
            db.session.add(user)

        user.name = user_info["name"]
        user.email_address = user_info["email_address"]
        user.mobile_number = user_info["mobile_number"]
        user.auth_type = user_info["auth_type"]
        user.password = user_info["password"]
        user.state = user_info["state"]
        user.email_access_validated_at = datetime.now(UTC).replace(tzinfo=None)
        user.platform_admin = False

        permissions = [
            Permission(service_id=user_info["service_id"], user_id=user.id, permission=p)
            for p in user_info["permissions"]
        ]

        service = Service.query.filter_by(id=user_info["service_id"]).one()
        if created:
            dao_add_user_to_service(service, user, permissions)
        else:
            permission_dao.set_user_service_permission(user, service, permissions, replace=True)

        # Remove user from any organisations it's in, so that we can cleanly set it up according to the current
        # request
        for organisation in user.organisations:
            dao_remove_user_from_organisation(organisation=organisation, user=user)

        organisation_id = user_info.get("organisation_id")
        if organisation_id:
            dao_get_organisation_by_id(organisation_id)
            dao_add_user_to_organisation(organisation_id, str(user.id), [])

        db.session.commit()

    return "ok", 201
