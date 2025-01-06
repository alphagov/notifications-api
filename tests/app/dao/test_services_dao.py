import uuid
from datetime import datetime, timedelta
from unittest import mock

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.constants import (
    EMAIL_TYPE,
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_SMS_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    SMS_TYPE,
    UPLOAD_LETTERS,
)
from app.dao.inbound_numbers_dao import (
    dao_get_available_inbound_numbers,
    dao_set_inbound_number_active_flag,
    dao_set_inbound_number_to_service,
)
from app.dao.organisation_dao import dao_add_service_to_organisation
from app.dao.service_permissions_dao import (
    dao_add_service_permission,
    dao_remove_service_permission,
)
from app.dao.service_user_dao import (
    dao_get_service_user,
    dao_update_service_user,
)
from app.dao.services_dao import (
    dao_add_user_to_service,
    dao_create_service,
    dao_fetch_active_users_for_service,
    dao_fetch_all_services,
    dao_fetch_all_services_by_user,
    dao_fetch_live_services_data,
    dao_fetch_service_by_id,
    dao_fetch_service_by_inbound_number,
    dao_fetch_todays_stats_for_all_services,
    dao_fetch_todays_stats_for_service,
    dao_find_services_sending_to_tv_numbers,
    dao_find_services_with_high_failure_rates,
    dao_remove_user_from_service,
    dao_update_service,
    delete_service_and_all_associated_db_objects,
    get_live_services_with_organisation,
    get_services_by_partial_name,
)
from app.dao.users_dao import create_user_code, save_model_user
from app.models import (
    ApiKey,
    InvitedUser,
    Job,
    Notification,
    NotificationHistory,
    Organisation,
    Permission,
    Service,
    ServicePermission,
    ServiceUser,
    Template,
    TemplateHistory,
    User,
    VerifyCode,
    user_folder_permissions,
)
from tests.app.db import (
    create_annual_billing,
    create_api_key,
    create_email_branding,
    create_ft_billing,
    create_inbound_number,
    create_invited_user,
    create_letter_branding,
    create_notification,
    create_notification_history,
    create_organisation,
    create_service,
    create_service_with_defined_sms_sender,
    create_service_with_inbound_number,
    create_template,
    create_template_folder,
    create_user,
)


def test_create_service(notify_db_session):
    user = create_user()
    create_letter_branding()
    assert Service.query.count() == 0
    service = Service(
        name="service name",
        restricted=False,
        organisation_type="central",
        created_by=user,
    )
    dao_create_service(service, user)
    assert Service.query.count() == 1
    service_db = Service.query.one()
    assert service_db.name == "service name"
    assert service_db.id == service.id
    assert service_db.email_sender_local_part == "service.name"
    assert service_db.prefix_sms is False
    assert service.active is True
    assert user in service_db.users
    assert service_db.organisation_type == "central"
    assert service_db.crown is None
    assert not service.letter_branding
    assert not service.organisation_id


def test_create_service_with_organisation(notify_db_session):
    user = create_user(email="local.authority@local-authority.gov.uk")
    organisation = create_organisation(
        name="Some local authority", organisation_type="local", domains=["local-authority.gov.uk"]
    )
    assert Service.query.count() == 0
    service = Service(
        name="service_name",
        restricted=False,
        organisation_type="central",
        created_by=user,
    )
    dao_create_service(service, user)
    assert Service.query.count() == 1
    service_db = Service.query.one()
    organisation = Organisation.query.get(organisation.id)
    assert service_db.name == "service_name"
    assert service_db.id == service.id
    assert service_db.prefix_sms is False
    assert service.active is True
    assert user in service_db.users
    assert service_db.organisation_type == "local"
    assert service_db.crown is None
    assert not service.letter_branding
    assert service.organisation_id == organisation.id
    assert service.organisation == organisation


@pytest.mark.parametrize(
    "email_address, organisation_type",
    (
        ("test@example.gov.uk", "nhs_central"),
        ("test@example.gov.uk", "nhs_local"),
        ("test@example.gov.uk", "nhs_gp"),
        ("test@nhs.net", "nhs_local"),
        ("test@nhs.net", "local"),
        ("test@nhs.net", "central"),
        ("test@nhs.uk", "central"),
        ("test@example.nhs.uk", "central"),
        ("TEST@NHS.UK", "central"),
    ),
)
@pytest.mark.parametrize(
    "branding_name_to_create, expected_branding",
    (
        ("NHS", True),
        # Need to check that nothing breaks in environments that don’t have
        # the NHS branding set up
        ("SHN", False),
    ),
)
def test_create_nhs_service_get_default_branding_based_on_email_address(
    notify_db_session,
    branding_name_to_create,
    expected_branding,
    email_address,
    organisation_type,
):
    user = create_user(email=email_address)
    letter_branding = create_letter_branding(name=branding_name_to_create)
    email_branding = create_email_branding(name=branding_name_to_create)

    service = Service(
        name="service_name",
        restricted=False,
        organisation_type=organisation_type,
        created_by=user,
    )
    dao_create_service(service, user)
    service_db = Service.query.one()

    if expected_branding:
        assert service_db.letter_branding == letter_branding
        assert service_db.email_branding == email_branding
    else:
        assert service_db.letter_branding is None
        assert service_db.email_branding is None


def test_cannot_create_two_services_with_same_name(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service1 = Service(
        name="service_name",
        restricted=False,
        created_by=user,
    )

    service2 = Service(
        name="service_name",
        restricted=False,
        created_by=user,
    )
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, user)
        dao_create_service(service2, user)
    assert 'duplicate key value violates unique constraint "services_name_key"' in str(excinfo.value)


def test_cannot_create_two_services_with_same_normalised_service_name(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service1 = Service(name="some name", restricted=False, created_by=user)
    service2 = Service(name="some (name)", restricted=False, created_by=user)
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, user)
        dao_create_service(service2, user)
    assert 'duplicate key value violates unique constraint "services_normalised_service_name_key"' in str(excinfo.value)


def test_cannot_create_service_with_no_user(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service = Service(name="service_name", restricted=False, created_by=user)
    with pytest.raises(ValueError) as excinfo:
        dao_create_service(service, None)
    assert "Can't create a service without a user" in str(excinfo.value)


def test_should_add_user_to_service(notify_db_session):
    user = create_user()
    service = Service(name="service_name", restricted=False, created_by=user)
    dao_create_service(service, user)
    assert user in Service.query.first().users
    new_user = User(
        name="Test User",
        email_address="new_user@digital.cabinet-office.gov.uk",
        password="password",
        mobile_number="+447700900986",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users


def test_dao_add_user_to_service_sets_folder_permissions(sample_user, sample_service):
    folder_1 = create_template_folder(sample_service)
    folder_2 = create_template_folder(sample_service)

    assert not folder_1.users
    assert not folder_2.users

    folder_permissions = [str(folder_1.id), str(folder_2.id)]

    dao_add_user_to_service(sample_service, sample_user, folder_permissions=folder_permissions)

    service_user = dao_get_service_user(user_id=sample_user.id, service_id=sample_service.id)
    assert len(service_user.folders) == 2
    assert folder_1 in service_user.folders
    assert folder_2 in service_user.folders


def test_dao_add_user_to_service_ignores_folders_which_do_not_exist_when_setting_permissions(
    sample_user, sample_service, fake_uuid
):
    valid_folder = create_template_folder(sample_service)
    folder_permissions = [fake_uuid, str(valid_folder.id)]

    dao_add_user_to_service(sample_service, sample_user, folder_permissions=folder_permissions)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)

    assert service_user.folders == [valid_folder]


def test_dao_add_user_to_service_raises_error_if_adding_folder_permissions_for_a_different_service(
    sample_service,
):
    user = create_user()
    other_service = create_service(service_name="other service")
    other_service_folder = create_template_folder(other_service)
    folder_permissions = [str(other_service_folder.id)]

    assert ServiceUser.query.count() == 2

    with pytest.raises(IntegrityError) as e:
        dao_add_user_to_service(sample_service, user, folder_permissions=folder_permissions)

    db.session.rollback()
    assert 'insert or update on table "user_folder_permissions" violates foreign key constraint' in str(e.value)
    assert ServiceUser.query.count() == 2


def test_should_remove_user_from_service(notify_db_session):
    user = create_user()
    service = Service(name="service_name", restricted=False, created_by=user)
    dao_create_service(service, user)
    new_user = User(
        name="Test User",
        email_address="new_user@digital.cabinet-office.gov.uk",
        password="password",
        mobile_number="+447700900986",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users
    dao_remove_user_from_service(service, new_user)
    assert new_user not in Service.query.first().users


def test_removing_a_user_from_a_service_deletes_their_permissions(sample_user, sample_service):
    assert len(Permission.query.all()) == 8

    dao_remove_user_from_service(sample_service, sample_user)

    assert Permission.query.all() == []


def test_removing_a_user_from_a_service_deletes_their_folder_permissions_for_that_service(sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_2 = create_service(sample_user, service_name="other service")
    tf3 = create_template_folder(service_2)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    service_2_user = dao_get_service_user(sample_user.id, service_2.id)
    service_2_user.folders = [tf3]
    dao_update_service_user(service_2_user)

    dao_remove_user_from_service(sample_service, sample_user)

    user_folder_permission = db.session.query(user_folder_permissions).one()
    assert user_folder_permission.user_id == service_2_user.user_id
    assert user_folder_permission.service_id == service_2_user.service_id
    assert user_folder_permission.template_folder_id == tf3.id


def test_get_all_services(notify_db_session):
    create_service(service_name="service 1")
    assert len(dao_fetch_all_services()) == 1
    assert dao_fetch_all_services()[0].name == "service 1"

    create_service(service_name="service 2")
    assert len(dao_fetch_all_services()) == 2
    assert dao_fetch_all_services()[1].name == "service 2"


def test_get_all_services_should_return_in_created_order(notify_db_session):
    create_service(service_name="service 1")
    create_service(service_name="service 2")
    create_service(service_name="service 3")
    create_service(service_name="service 4")
    assert len(dao_fetch_all_services()) == 4
    assert dao_fetch_all_services()[0].name == "service 1"
    assert dao_fetch_all_services()[1].name == "service 2"
    assert dao_fetch_all_services()[2].name == "service 3"
    assert dao_fetch_all_services()[3].name == "service 4"


def test_get_all_services_should_return_empty_list_if_no_services():
    assert len(dao_fetch_all_services()) == 0


def test_get_all_services_for_user(notify_db_session):
    user = create_user()
    create_service(service_name="service 1", user=user)
    create_service(service_name="service 2", user=user)
    create_service(service_name="service 3", user=user)
    assert len(dao_fetch_all_services_by_user(user.id)) == 3
    assert dao_fetch_all_services_by_user(user.id)[0].name == "service 1"
    assert dao_fetch_all_services_by_user(user.id)[1].name == "service 2"
    assert dao_fetch_all_services_by_user(user.id)[2].name == "service 3"


def test_get_services_by_partial_name(notify_db_session):
    create_service(service_name="Tadfield Police")
    create_service(service_name="Tadfield Air Base")
    create_service(service_name="London M25 Management Body")
    services_from_db = get_services_by_partial_name("Tadfield")
    assert len(services_from_db) == 2
    assert sorted([service.name for service in services_from_db]) == ["Tadfield Air Base", "Tadfield Police"]


def test_get_services_by_partial_name_is_case_insensitive(notify_db_session):
    create_service(service_name="Tadfield Police")
    services_from_db = get_services_by_partial_name("tadfield")
    assert services_from_db[0].name == "Tadfield Police"


def test_get_all_user_services_only_returns_services_user_has_access_to(notify_db_session):
    user = create_user()
    create_service(service_name="service 1", user=user)
    create_service(service_name="service 2", user=user)
    service_3 = create_service(service_name="service 3", user=user)
    new_user = User(
        name="Test User",
        email_address="new_user@digital.cabinet-office.gov.uk",
        password="password",
        mobile_number="+447700900986",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service_3, new_user)
    assert len(dao_fetch_all_services_by_user(user.id)) == 3
    assert dao_fetch_all_services_by_user(user.id)[0].name == "service 1"
    assert dao_fetch_all_services_by_user(user.id)[1].name == "service 2"
    assert dao_fetch_all_services_by_user(user.id)[2].name == "service 3"
    assert len(dao_fetch_all_services_by_user(new_user.id)) == 1
    assert dao_fetch_all_services_by_user(new_user.id)[0].name == "service 3"


def test_get_all_user_services_should_return_empty_list_if_no_services_for_user(notify_db_session):
    user = create_user()
    assert len(dao_fetch_all_services_by_user(user.id)) == 0


@freeze_time("2019-04-23T10:00:00")
def test_dao_fetch_live_services_data(sample_user, nhs_email_branding, nhs_letter_branding):
    org = create_organisation(organisation_type="nhs_central")
    service = create_service(go_live_user=sample_user, go_live_at="2014-04-20T10:00:00")
    sms_template = create_template(service=service)
    service_2 = create_service(service_name="second", go_live_at="2017-04-20T10:00:00", go_live_user=sample_user)
    service_3 = create_service(service_name="third", go_live_at="2016-04-20T10:00:00")
    # below services should be filtered out:
    create_service(service_name="restricted", restricted=True)
    create_service(service_name="not_active", active=False)
    create_service(service_name="not_live", count_as_live=False)
    email_template = create_template(service=service, template_type="email")
    template_letter_1 = create_template(service=service, template_type="letter")
    template_letter_2 = create_template(service=service_2, template_type="letter")
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    # two sms billing records for 1st service within current financial year:
    create_ft_billing(bst_date="2019-04-20", template=sms_template)
    create_ft_billing(bst_date="2019-04-21", template=sms_template)
    # one sms billing record for 1st service from previous financial year, should not appear in the result:
    create_ft_billing(bst_date="2018-04-20", template=sms_template)
    # one email billing record for 1st service within current financial year:
    create_ft_billing(bst_date="2019-04-20", template=email_template)
    # one letter billing record for 1st service within current financial year:
    create_ft_billing(bst_date="2019-04-15", template=template_letter_1)
    # one letter billing record for 2nd service within current financial year:
    create_ft_billing(bst_date="2019-04-16", template=template_letter_2)

    # 1st service: billing from 2018 and 2019
    create_annual_billing(service.id, 500, 2018)
    create_annual_billing(service.id, 100, 2019)
    # 2nd service: billing from 2018
    create_annual_billing(service_2.id, 300, 2018)
    # 3rd service: billing from 2019
    create_annual_billing(service_3.id, 200, 2019)

    results = dao_fetch_live_services_data()
    assert len(results) == 3
    # checks the results and that they are ordered by date:
    assert results == [
        {
            "service_id": mock.ANY,
            "service_name": "Sample service",
            "organisation_name": "test_org_1",
            "organisation_type": "nhs_central",
            "consent_to_research": None,
            "contact_name": "Test User",
            "contact_email": "notify@digital.cabinet-office.gov.uk",
            "contact_mobile": "+447700900986",
            "live_date": datetime(2014, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "email_volume_intent": None,
            "letter_volume_intent": None,
            "sms_totals": 2,
            "email_totals": 1,
            "letter_totals": 1,
            "free_sms_fragment_limit": 100,
        },
        {
            "service_id": mock.ANY,
            "service_name": "third",
            "organisation_name": None,
            "consent_to_research": None,
            "organisation_type": None,
            "contact_name": None,
            "contact_email": None,
            "contact_mobile": None,
            "live_date": datetime(2016, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "email_volume_intent": None,
            "letter_volume_intent": None,
            "sms_totals": 0,
            "email_totals": 0,
            "letter_totals": 0,
            "free_sms_fragment_limit": 200,
        },
        {
            "service_id": mock.ANY,
            "service_name": "second",
            "organisation_name": None,
            "consent_to_research": None,
            "contact_name": "Test User",
            "contact_email": "notify@digital.cabinet-office.gov.uk",
            "contact_mobile": "+447700900986",
            "live_date": datetime(2017, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "organisation_type": None,
            "email_volume_intent": None,
            "letter_volume_intent": None,
            "sms_totals": 0,
            "email_totals": 0,
            "letter_totals": 1,
            "free_sms_fragment_limit": 300,
        },
    ]


def test_get_service_by_id_returns_none_if_no_service(notify_db_session):
    with pytest.raises(NoResultFound) as e:
        dao_fetch_service_by_id(str(uuid.uuid4()))
    assert "No row was found when one was required" in str(e.value)


def test_get_service_by_id_returns_service(notify_db_session):
    service = create_service(service_name="testing")
    assert dao_fetch_service_by_id(service.id).name == "testing"


def test_create_service_returns_service_with_default_permissions(notify_db_session):
    service = create_service(service_name="testing", service_permissions=None)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(
        service.permissions,
        (SMS_TYPE, EMAIL_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS),
    )


@pytest.mark.parametrize(
    "permission_to_remove, permissions_remaining",
    [
        (SMS_TYPE, (EMAIL_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS)),
        (EMAIL_TYPE, (SMS_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS)),
    ],
)
def test_remove_permission_from_service_by_id_returns_service_with_correct_permissions(
    notify_db_session, permission_to_remove, permissions_remaining
):
    service = create_service(service_permissions=None)
    dao_remove_service_permission(service_id=service.id, permission=permission_to_remove)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(service.permissions, permissions_remaining)


def test_removing_all_permission_returns_service_with_no_permissions(notify_db_session):
    service = create_service()
    dao_remove_service_permission(service_id=service.id, permission=SMS_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=EMAIL_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=INTERNATIONAL_SMS_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=UPLOAD_LETTERS)
    dao_remove_service_permission(service_id=service.id, permission=INTERNATIONAL_LETTERS)

    service = dao_fetch_service_by_id(service.id)
    assert len(service.permissions) == 0


def test_create_service_by_id_adding_and_removing_letter_returns_service_without_letter(service_factory):
    service = service_factory.get("testing")

    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    dao_add_service_permission(service_id=service.id, permission=LETTER_TYPE)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(
        service.permissions,
        (SMS_TYPE, EMAIL_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS),
    )

    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    service = dao_fetch_service_by_id(service.id)

    _assert_service_permissions(
        service.permissions, (SMS_TYPE, EMAIL_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS)
    )


def test_create_service_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    create_letter_branding()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(
        name="service_name",
        restricted=False,
        created_by=user,
        custom_email_sender_name="email sender",
    )
    dao_create_service(service, user)
    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 1

    service_from_db = Service.query.first()
    service_history = Service.get_history_model().query.first()

    assert service_from_db.id == service_history.id
    assert service_from_db.name == service_history.name
    assert service_from_db.version == 1
    assert service_from_db.version == service_history.version
    assert user.id == service_history.created_by_id
    assert service_from_db.created_by.id == service_history.created_by_id
    assert service_history.custom_email_sender_name == "email sender"
    assert service_history.email_sender_local_part == "email.sender"


def test_update_service_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="service_name", restricted=False, created_by=user)
    dao_create_service(service, user)

    assert Service.query.count() == 1
    assert Service.query.first().version == 1
    assert Service.get_history_model().query.count() == 1

    service.name = "updated_service_name"
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 2

    service_from_db = Service.query.first()

    assert service_from_db.version == 2

    assert Service.get_history_model().query.filter_by(name="service_name").one().version == 1
    assert Service.get_history_model().query.filter_by(name="updated_service_name").one().version == 2


def test_update_service_permission_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="service_name", restricted=False, created_by=user)
    dao_create_service(
        service,
        user,
        service_permissions=[
            SMS_TYPE,
            EMAIL_TYPE,
            INTERNATIONAL_SMS_TYPE,
        ],
    )

    service.permissions.append(ServicePermission(service_id=service.id, permission="letter"))
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 2

    service_from_db = Service.query.first()

    assert service_from_db.version == 2

    _assert_service_permissions(
        service.permissions,
        (
            SMS_TYPE,
            EMAIL_TYPE,
            INTERNATIONAL_SMS_TYPE,
            LETTER_TYPE,
        ),
    )

    permission = [p for p in service.permissions if p.permission == "sms"][0]
    service.permissions.remove(permission)
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 3

    service_from_db = Service.query.first()
    assert service_from_db.version == 3
    _assert_service_permissions(
        service.permissions,
        (
            EMAIL_TYPE,
            INTERNATIONAL_SMS_TYPE,
            LETTER_TYPE,
        ),
    )

    history = Service.get_history_model().query.filter_by(name="service_name").order_by("version").all()

    assert len(history) == 3
    assert history[2].version == 3


def test_create_service_and_history_is_transactional(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name="foo", restricted=False, created_by=None)

    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service, user)

    assert 'column "created_by_id" of relation "services_history" violates not-null constraint' in str(excinfo.value)
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0


def test_delete_service_and_associated_objects(notify_db_session):
    user = create_user()
    organisation = create_organisation()
    service = create_service(user=user, service_permissions=None, organisation=organisation)
    create_user_code(user=user, code="somecode", code_type="email")
    create_user_code(user=user, code="somecode", code_type="sms")
    template = create_template(service=service)
    api_key = create_api_key(service=service)
    create_notification(template=template, api_key=api_key)
    create_invited_user(service=service)
    user.organisations = [organisation]

    assert ServicePermission.query.count() == len(
        (SMS_TYPE, EMAIL_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS)
    )

    delete_service_and_all_associated_db_objects(service)
    assert VerifyCode.query.count() == 0
    assert ApiKey.query.count() == 0
    assert ApiKey.get_history_model().query.count() == 0
    assert Template.query.count() == 0
    assert TemplateHistory.query.count() == 0
    assert Job.query.count() == 0
    assert Notification.query.count() == 0
    assert Permission.query.count() == 0
    assert InvitedUser.query.count() == 0
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    assert ServicePermission.query.count() == 0
    # we don't delete users as part of this function (see delete_user_and_all_associated_db_objects)
    assert User.query.count() == 1
    # the organisation hasn't been deleted
    assert Organisation.query.count() == 1


def test_add_existing_user_to_another_service_doesnot_change_old_permissions(notify_db_session):
    user = create_user()

    service_one = Service(name="service_one", restricted=False, created_by=user)

    dao_create_service(service_one, user)
    assert user.id == service_one.users[0].id
    test_user_permissions = Permission.query.filter_by(service=service_one, user=user).all()
    assert len(test_user_permissions) == 8

    other_user = User(
        name="Other Test User",
        email_address="other_user@digital.cabinet-office.gov.uk",
        password="password",
        mobile_number="+447700900987",
    )
    save_model_user(other_user, validated_email_access=True)
    service_two = Service(name="service_two", restricted=False, created_by=other_user)
    dao_create_service(service_two, other_user)

    assert other_user.id == service_two.users[0].id
    other_user_permissions = Permission.query.filter_by(service=service_two, user=other_user).all()
    assert len(other_user_permissions) == 8

    other_user_service_one_permissions = Permission.query.filter_by(service=service_one, user=other_user).all()
    assert len(other_user_service_one_permissions) == 0

    # adding the other_user to service_one should leave all other_user permissions on service_two intact
    permissions = []
    for p in ["send_emails", "send_texts", "send_letters"]:
        permissions.append(Permission(permission=p))

    dao_add_user_to_service(service_one, other_user, permissions=permissions)

    other_user_service_one_permissions = Permission.query.filter_by(service=service_one, user=other_user).all()
    assert len(other_user_service_one_permissions) == 3

    other_user_service_two_permissions = Permission.query.filter_by(service=service_two, user=other_user).all()
    assert len(other_user_service_two_permissions) == 8


def test_fetch_stats_filters_on_service(notify_db_session):
    service_one = create_service()
    create_notification(template=create_template(service=service_one))

    service_two = Service(
        name="service_two",
        created_by=service_one.created_by,
        restricted=False,
        email_message_limit=1000,
        sms_message_limit=1000,
        letter_message_limit=1000,
    )
    dao_create_service(service_two, service_one.created_by)

    stats = dao_fetch_todays_stats_for_service(service_two.id)
    assert len(stats) == 0


def test_fetch_stats_ignores_historical_notification_data(sample_template):
    create_notification_history(template=sample_template)

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 1

    stats = dao_fetch_todays_stats_for_service(sample_template.service_id)
    assert len(stats) == 0


def test_dao_fetch_todays_stats_for_service(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service)
    email_template = create_template(service=service, template_type="email")
    # two created email, one failed email, and one created sms
    create_notification(template=email_template, status="created")
    create_notification(template=email_template, status="created")
    create_notification(template=email_template, status="technical-failure")
    create_notification(template=sms_template, status="created")

    stats = dao_fetch_todays_stats_for_service(service.id)
    stats = sorted(stats, key=lambda x: (x.notification_type, x.status))
    assert len(stats) == 3

    assert stats[0].notification_type == "email"
    assert stats[0].status == "created"
    assert stats[0].count == 2

    assert stats[1].notification_type == "email"
    assert stats[1].status == "technical-failure"
    assert stats[1].count == 1

    assert stats[2].notification_type == "sms"
    assert stats[2].status == "created"
    assert stats[2].count == 1


def test_dao_fetch_todays_stats_for_service_should_ignore_test_key(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    live_api_key = create_api_key(service=service, key_type=KEY_TYPE_NORMAL)
    team_api_key = create_api_key(service=service, key_type=KEY_TYPE_TEAM)
    test_api_key = create_api_key(service=service, key_type=KEY_TYPE_TEST)

    # two created email, one failed email, and one created sms
    create_notification(template=template, api_key=live_api_key, key_type=live_api_key.key_type)
    create_notification(template=template, api_key=test_api_key, key_type=test_api_key.key_type)
    create_notification(template=template, api_key=team_api_key, key_type=team_api_key.key_type)
    create_notification(template=template)

    stats = dao_fetch_todays_stats_for_service(service.id)
    assert len(stats) == 1
    assert stats[0].notification_type == "sms"
    assert stats[0].status == "created"
    assert stats[0].count == 3


def test_dao_fetch_todays_stats_for_service_only_includes_today(notify_db_session):
    template = create_template(service=create_service())
    # two created email, one failed email, and one created sms
    with freeze_time("2001-01-01T23:59:00"):
        # just_before_midnight_yesterday
        create_notification(template=template, to_field="1", status="delivered")

    with freeze_time("2001-01-02T00:01:00"):
        # just_after_midnight_today
        create_notification(template=template, to_field="2", status="failed")

    with freeze_time("2001-01-02T12:00:00"):
        # right_now
        create_notification(template=template, to_field="3", status="created")

        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert "delivered" not in stats
    assert stats["failed"] == 1
    assert stats["created"] == 1


def test_dao_fetch_todays_stats_for_service_only_includes_today_when_clocks_spring_forward(notify_db_session):
    template = create_template(service=create_service())
    with freeze_time("2021-03-27T23:59:59"):
        # just before midnight yesterday in UTC -- not included
        create_notification(template=template, to_field="1", status="permanent-failure")
    with freeze_time("2021-03-28T00:01:00"):
        # just after midnight yesterday in UTC -- included
        create_notification(template=template, to_field="2", status="failed")
    with freeze_time("2021-03-28T12:00:00"):
        # we have entered BST at this point but had not for the previous two notifications --included
        # collect stats for this timestamp
        create_notification(template=template, to_field="3", status="created")
        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert "delivered" not in stats
    assert stats["failed"] == 1
    assert stats["created"] == 1
    assert not stats.get("permanent-failure")
    assert not stats.get("temporary-failure")


def test_dao_fetch_todays_stats_for_service_only_includes_today_during_bst(notify_db_session):
    template = create_template(service=create_service())
    with freeze_time("2021-03-28T22:59:59"):
        # just before midnight BST -- not included
        create_notification(template=template, to_field="1", status="permanent-failure")
    with freeze_time("2021-03-28T23:00:01"):
        # just after midnight BST -- included
        create_notification(template=template, to_field="2", status="failed")
    with freeze_time("2021-03-29T12:00:00"):
        # well after midnight BST -- included
        # collect stats for this timestamp
        create_notification(template=template, to_field="3", status="created")
        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert "delivered" not in stats
    assert stats["failed"] == 1
    assert stats["created"] == 1
    assert not stats.get("permanent-failure")


def test_dao_fetch_todays_stats_for_service_only_includes_today_when_clocks_fall_back(notify_db_session):
    template = create_template(service=create_service())
    with freeze_time("2021-10-30T22:59:59"):
        # just before midnight BST -- not included
        create_notification(template=template, to_field="1", status="permanent-failure")
    with freeze_time("2021-10-31T23:00:01"):
        # just after midnight BST -- included
        create_notification(template=template, to_field="2", status="failed")
    # clocks go back to UTC on 31 October at 2am
    with freeze_time("2021-10-31T12:00:00"):
        # well after midnight -- included
        # collect stats for this timestamp
        create_notification(template=template, to_field="3", status="created")
        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert "delivered" not in stats
    assert stats["failed"] == 1
    assert stats["created"] == 1
    assert not stats.get("permanent-failure")


def test_dao_fetch_todays_stats_for_service_only_includes_during_utc(notify_db_session):
    template = create_template(service=create_service())
    with freeze_time("2021-10-30T12:59:59"):
        # just before midnight UTC -- not included
        create_notification(template=template, to_field="1", status="permanent-failure")
    with freeze_time("2021-10-31T00:00:01"):
        # just after midnight UTC -- included
        create_notification(template=template, to_field="2", status="failed")
    # clocks go back to UTC on 31 October at 2am
    with freeze_time("2021-10-31T12:00:00"):
        # well after midnight -- included
        # collect stats for this timestamp
        create_notification(template=template, to_field="3", status="created")
        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert "delivered" not in stats
    assert stats["failed"] == 1
    assert stats["created"] == 1
    assert not stats.get("permanent-failure")


def test_dao_fetch_todays_stats_for_all_services_includes_all_services(notify_db_session):
    # two services, each with an email and sms notification
    service1 = create_service(service_name="service 1")
    service2 = create_service(service_name="service 2")
    template_email_one = create_template(service=service1, template_type="email")
    template_sms_one = create_template(service=service1, template_type="sms")
    template_email_two = create_template(service=service2, template_type="email")
    template_sms_two = create_template(service=service2, template_type="sms")
    create_notification(template=template_email_one)
    create_notification(template=template_sms_one)
    create_notification(template=template_email_two)
    create_notification(template=template_sms_two)

    stats = dao_fetch_todays_stats_for_all_services()

    assert len(stats) == 4
    # services are ordered by service id; not explicit on email/sms or status
    assert stats == sorted(stats, key=lambda x: x.service_id)


def test_dao_fetch_todays_stats_for_all_services_only_includes_today(notify_db_session):
    template = create_template(service=create_service())
    with freeze_time("2001-01-01T23:59:00"):
        # just_before_midnight_yesterday
        create_notification(template=template, to_field="1", status="delivered")

    with freeze_time("2001-01-02T00:01:00"):
        # just_after_midnight_today
        create_notification(template=template, to_field="2", status="failed")

    with freeze_time("2001-01-02T12:00:00"):
        stats = dao_fetch_todays_stats_for_all_services()

    stats = {row.status: row.count for row in stats}
    assert "delivered" not in stats
    assert stats["failed"] == 1


def test_dao_fetch_todays_stats_for_all_services_groups_correctly(notify_db_session):
    service1 = create_service(service_name="service 1")
    service2 = create_service(service_name="service 2")
    template_sms = create_template(service=service1)
    template_email = create_template(service=service1, template_type="email")
    template_two = create_template(service=service2)
    # service1: 2 sms with status "created" and one "failed", and one email
    create_notification(template=template_sms)
    create_notification(template=template_sms)
    create_notification(template=template_sms, status="failed")
    create_notification(template=template_email)
    # service2: 1 sms "created"
    create_notification(template=template_two)

    stats = dao_fetch_todays_stats_for_all_services()
    assert len(stats) == 4
    assert (
        service1.id,
        service1.name,
        service1.restricted,
        service1.active,
        service1.created_at,
        "sms",
        "created",
        2,
    ) in stats
    assert (
        service1.id,
        service1.name,
        service1.restricted,
        service1.active,
        service1.created_at,
        "sms",
        "failed",
        1,
    ) in stats
    assert (
        service1.id,
        service1.name,
        service1.restricted,
        service1.active,
        service1.created_at,
        "email",
        "created",
        1,
    ) in stats
    assert (
        service2.id,
        service2.name,
        service2.restricted,
        service2.active,
        service2.created_at,
        "sms",
        "created",
        1,
    ) in stats


def test_dao_fetch_todays_stats_for_all_services_includes_all_keys_by_default(notify_db_session):
    template = create_template(service=create_service())
    create_notification(template=template, key_type=KEY_TYPE_NORMAL)
    create_notification(template=template, key_type=KEY_TYPE_TEAM)
    create_notification(template=template, key_type=KEY_TYPE_TEST)

    stats = dao_fetch_todays_stats_for_all_services()

    assert len(stats) == 1
    assert stats[0].count == 3


def test_dao_fetch_todays_stats_for_all_services_can_exclude_from_test_key(notify_db_session):
    template = create_template(service=create_service())
    create_notification(template=template, key_type=KEY_TYPE_NORMAL)
    create_notification(template=template, key_type=KEY_TYPE_TEAM)
    create_notification(template=template, key_type=KEY_TYPE_TEST)

    stats = dao_fetch_todays_stats_for_all_services(include_from_test_key=False)

    assert len(stats) == 1
    assert stats[0].count == 2


def test_dao_fetch_active_users_for_service_returns_active_only(notify_db_session):
    active_user = create_user(email="active@foo.com", state="active")
    pending_user = create_user(email="pending@foo.com", state="pending")
    service = create_service(user=active_user)
    dao_add_user_to_service(service, pending_user)
    users = dao_fetch_active_users_for_service(service.id)

    assert len(users) == 1


def test_dao_fetch_service_by_inbound_number_with_inbound_number(notify_db_session):
    foo1 = create_service_with_inbound_number(service_name="a", inbound_number="1")
    create_service_with_defined_sms_sender(service_name="b", sms_sender_value="2")
    create_service_with_defined_sms_sender(service_name="c", sms_sender_value="3")
    create_inbound_number("2")
    create_inbound_number("3")

    service = dao_fetch_service_by_inbound_number("1")

    assert foo1.id == service.id


def test_dao_fetch_service_by_inbound_number_with_inbound_number_not_set(notify_db_session):
    create_inbound_number("1")

    service = dao_fetch_service_by_inbound_number("1")

    assert service is None


def test_dao_fetch_service_by_inbound_number_when_inbound_number_set(notify_db_session):
    service_1 = create_service_with_inbound_number(inbound_number="1", service_name="a")
    create_service(service_name="b")

    service = dao_fetch_service_by_inbound_number("1")

    assert service.id == service_1.id


def test_dao_fetch_service_by_inbound_number_with_unknown_number(notify_db_session):
    create_service_with_inbound_number(inbound_number="1", service_name="a")

    service = dao_fetch_service_by_inbound_number("9")

    assert service is None


def test_dao_fetch_service_by_inbound_number_with_inactive_number_returns_empty(notify_db_session):
    service = create_service_with_inbound_number(inbound_number="1", service_name="a")
    dao_set_inbound_number_active_flag(service_id=service.id, active=False)

    service = dao_fetch_service_by_inbound_number("1")

    assert service is None


def test_dao_allocating_inbound_number_shows_on_service(notify_db_session):
    create_service_with_inbound_number()
    create_inbound_number(number="07700900003")

    inbound_numbers = dao_get_available_inbound_numbers()

    service = create_service(service_name="test service")

    dao_set_inbound_number_to_service(service.id, inbound_numbers[0])

    assert service.inbound_number.number == inbound_numbers[0].number


def _assert_service_permissions(service_permissions, expected):
    assert len(service_permissions) == len(expected)
    assert set(expected) == {p.permission for p in service_permissions}


def create_email_sms_letter_template():
    service = create_service()
    template_one = create_template(service=service, template_name="1", template_type="email")
    template_two = create_template(service=service, template_name="2", template_type="sms")
    template_three = create_template(service=service, template_name="3", template_type="letter")
    return template_one, template_three, template_two


@freeze_time("2019-12-02 12:00:00.000000")
def test_dao_find_services_sending_to_tv_numbers(notify_db_session, fake_uuid):
    service_1 = create_service(service_name="Service 1", service_id=fake_uuid)
    service_3 = create_service(service_name="Service 3", restricted=True)  # restricted is excluded
    service_4 = create_service(service_name="Service 4", active=False)  # not active is excluded
    services = [service_1, service_3, service_4]

    tv_number = "447700900001"
    normal_number = "447711900001"
    normal_number_resembling_tv_number = "447227700900"

    for service in services:
        template = create_template(service)
        for _ in range(5):
            create_notification(template, normalised_to=tv_number, status="permanent-failure")

    service_5 = create_service(service_name="Service 6")  # notifications too old are excluded
    with freeze_time("2019-11-30 15:00:00.000000"):
        template_5 = create_template(service_5)
        for _ in range(5):
            create_notification(template_5, normalised_to=tv_number, status="permanent-failure")

    service_2 = create_service(service_name="Service 2")  # below threshold is excluded
    template_2 = create_template(service_2)
    create_notification(template_2, normalised_to=tv_number, status="permanent-failure")
    for _ in range(5):
        # test key type is excluded
        create_notification(template_2, normalised_to=tv_number, status="permanent-failure", key_type="test")
    for _ in range(5):
        # normal numbers are not counted by the query
        create_notification(template_2, normalised_to=normal_number, status="delivered")
        create_notification(template_2, normalised_to=normal_number_resembling_tv_number, status="delivered")

    start_date = datetime.utcnow() - timedelta(days=1)
    end_date = datetime.utcnow()

    result = dao_find_services_sending_to_tv_numbers(start_date, end_date, threshold=4)
    assert len(result) == 1
    assert str(result[0].service_id) == fake_uuid


def test_dao_find_services_with_high_failure_rates(notify_db_session, fake_uuid):
    service_1 = create_service(service_name="Service 1", service_id=fake_uuid)
    service_3 = create_service(service_name="Service 3", restricted=True)  # restricted is excluded
    service_4 = create_service(service_name="Service 4", active=False)  # not active is excluded
    services = [service_1, service_3, service_4]

    for service in services:
        template = create_template(service)
        for _ in range(3):
            create_notification(template, status="permanent-failure")
            create_notification(template, status="delivered")
            create_notification(template, status="sending")
            create_notification(template, status="temporary-failure")

    service_5 = create_service(service_name="Service 5")
    with freeze_time("2019-11-30 15:00:00.000000"):
        template_5 = create_template(service_5)
        for _ in range(4):
            create_notification(template_5, status="permanent-failure")  # notifications too old are excluded

    service_2 = create_service(service_name="Service 2")
    template_2 = create_template(service_2)
    for _ in range(4):
        create_notification(template_2, status="permanent-failure", key_type="test")  # test key type is excluded
    create_notification(template_2, status="permanent-failure")  # below threshold is excluded

    start_date = datetime.utcnow() - timedelta(days=1)
    end_date = datetime.utcnow()

    result = dao_find_services_with_high_failure_rates(start_date, end_date, threshold=3)
    # assert len(result) == 3
    # assert str(result[0].service_id) == fake_uuid
    assert len(result) == 1
    assert str(result[0].service_id) == fake_uuid
    assert result[0].permanent_failure_rate == 0.25


def test_get_live_services_with_organisation(sample_organisation):
    trial_service = create_service(service_name="trial service", restricted=True)
    live_service = create_service(service_name="count as live")
    live_service_diff_org = create_service(service_name="live service different org")
    dont_count_as_live = create_service(service_name="dont count as live", count_as_live=False)
    inactive_service = create_service(service_name="inactive", active=False)
    service_without_org = create_service(service_name="no org")
    another_org = create_organisation(
        name="different org",
    )

    dao_add_service_to_organisation(trial_service, sample_organisation.id)
    dao_add_service_to_organisation(live_service, sample_organisation.id)
    dao_add_service_to_organisation(dont_count_as_live, sample_organisation.id)
    dao_add_service_to_organisation(inactive_service, sample_organisation.id)
    dao_add_service_to_organisation(live_service_diff_org, another_org.id)

    services = get_live_services_with_organisation()
    assert len(services) == 3
    assert ([(x.service_name, x.organisation_name) for x in services]) == [
        (live_service_diff_org.name, another_org.name),
        (live_service.name, sample_organisation.name),
        (service_without_org.name, None),
    ]
