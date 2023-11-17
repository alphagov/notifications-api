import datetime

import freezegun
import pytest
from flask import url_for

from app.models import User
from tests.app.db import create_organisation, create_service, create_user


class TestCreateFunctionalTestUsers:
    @pytest.fixture(autouse=True)
    def notify_db_session(self, notify_db_session):
        return notify_db_session

    def test_auth_required(self, client):
        response = client.put(url_for("functional_tests.create_functional_test_users"), data="[]")
        assert response.status_code == 401

    def test_201(self, functional_tests_request):
        functional_tests_request.put("functional_tests.create_functional_test_users", _data=[], _expected_status=201)

    def test_user_created(self, functional_tests_request):
        organisation = create_organisation()
        service = create_service(organisation=organisation)
        functional_tests_request.put(
            "functional_tests.create_functional_test_users",
            _data=[
                {
                    "name": "my test user",
                    "email_address": "something@example.com",
                    "mobile_number": "07700900000",
                    "auth_type": "sms_auth",
                    "password": "hello",
                    "state": "active",
                    "permissions": ["send_emails", "send_letters", "send_texts"],
                    "service_id": str(service.id),
                    "organisation_id": str(organisation.id),
                }
            ],
            _expected_status=201,
        )

        user = User.query.filter_by(email_address="something@example.com").one()
        assert user.name == "my test user"
        assert user.mobile_number == "07700900000"
        assert user.auth_type == "sms_auth"
        assert user.state == "active"
        assert set(user.get_permissions()[str(service.id)]) == {"send_emails", "send_letters", "send_texts"}
        assert service in user.services
        assert organisation in user.organisations

    def test_user_updated(self, functional_tests_request, notify_db_session):
        organisation = create_organisation()
        service = create_service(organisation=organisation)
        user = create_user(
            name="my test user",
            email="something@example.com",
            mobile_number="07700900000",
            auth_type="sms_auth",
            password="bad old password",
            state="inactive",
            email_access_validated_at=datetime.datetime(2020, 1, 1, 12, 0, 0),
        )

        user.organisations.append(organisation)
        user.services.append(service)
        notify_db_session.commit()

        with freezegun.freeze_time("2020-06-01T13:00:00"):
            functional_tests_request.put(
                "functional_tests.create_functional_test_users",
                _data=[
                    {
                        "name": "my updated test user",
                        "email_address": "something@example.com",
                        "mobile_number": "07700900999",
                        "auth_type": "email_auth",
                        "password": "good new password",
                        "state": "active",
                        "permissions": ["send_emails", "send_letters", "send_texts"],
                        "service_id": str(service.id),
                        "organisation_id": str(organisation.id),
                    }
                ],
                _expected_status=201,
            )

        notify_db_session.refresh(user)
        assert user.id == user.id
        assert user.name == "my updated test user"
        assert user.mobile_number == "07700900999"
        assert user.auth_type == "email_auth"
        assert user.state == "active"
        assert set(user.get_permissions()[str(service.id)]) == {"send_emails", "send_letters", "send_texts"}
        assert user.email_access_validated_at == datetime.datetime(2020, 6, 1, 13)
