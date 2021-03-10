import datetime
import uuid

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db
from app.dao.organisation_dao import (
    dao_add_service_to_organisation,
    dao_add_user_to_organisation,
    dao_get_invited_organisation_user,
    dao_get_organisation_by_email_address,
    dao_get_organisation_by_id,
    dao_get_organisation_by_service_id,
    dao_get_organisation_services,
    dao_get_organisations,
    dao_get_users_for_organisation,
    dao_update_organisation,
)
from app.models import Organisation, Service
from tests.app.db import (
    create_domain,
    create_email_branding,
    create_letter_branding,
    create_organisation,
    create_service,
    create_user,
)


def test_get_organisations_gets_all_organisations_alphabetically_with_active_organisations_first(
        notify_db_session
):
    m_active_org = create_organisation(name='m_active_organisation')
    z_inactive_org = create_organisation(name='z_inactive_organisation', active=False)
    a_inactive_org = create_organisation(name='a_inactive_organisation', active=False)
    z_active_org = create_organisation(name='z_active_organisation')
    a_active_org = create_organisation(name='a_active_organisation')

    organisations = dao_get_organisations()

    assert len(organisations) == 5
    assert organisations[0] == a_active_org
    assert organisations[1] == m_active_org
    assert organisations[2] == z_active_org
    assert organisations[3] == a_inactive_org
    assert organisations[4] == z_inactive_org


def test_get_organisation_by_id_gets_correct_organisation(notify_db_session):
    organisation = create_organisation()

    organisation_from_db = dao_get_organisation_by_id(organisation.id)

    assert organisation_from_db == organisation


def test_update_organisation(notify_db_session):
    create_organisation()

    organisation = Organisation.query.one()
    user = create_user()
    email_branding = create_email_branding()
    letter_branding = create_letter_branding()

    data = {
        'name': 'new name',
        "crown": True,
        "organisation_type": 'local',
        "agreement_signed": True,
        "agreement_signed_at": datetime.datetime.utcnow(),
        "agreement_signed_by_id": user.id,
        "agreement_signed_version": 999.99,
        "letter_branding_id": letter_branding.id,
        "email_branding_id": email_branding.id,
    }

    for attribute, value in data.items():
        assert getattr(organisation, attribute) != value

    assert organisation.updated_at is None

    dao_update_organisation(organisation.id, **data)

    organisation = Organisation.query.one()

    for attribute, value in data.items():
        assert getattr(organisation, attribute) == value

    assert organisation.updated_at


@pytest.mark.parametrize('domain_list, expected_domains', (
    (['abc', 'def'], {'abc', 'def'}),
    (['ABC', 'DEF'], {'abc', 'def'}),
    ([], set()),
    (None, {'123', '456'}),
    pytest.param(
        ['abc', 'ABC'], {'abc'},
        marks=pytest.mark.xfail(raises=IntegrityError)
    ),
))
def test_update_organisation_domains_lowercases(
    notify_db_session,
    domain_list,
    expected_domains,
):
    create_organisation()

    organisation = Organisation.query.one()

    # Seed some domains
    dao_update_organisation(organisation.id, domains=['123', '456'])

    # This should overwrite the seeded domains
    dao_update_organisation(organisation.id, domains=domain_list)

    assert {domain.domain for domain in organisation.domains} == expected_domains


def test_update_organisation_does_not_update_the_service_if_certain_attributes_not_provided(
    sample_service,
    sample_organisation,
):
    email_branding = create_email_branding()
    letter_branding = create_letter_branding()

    sample_service.organisation_type = 'local'
    sample_organisation.organisation_type = 'central'
    sample_organisation.email_branding = email_branding
    sample_organisation.letter_branding = letter_branding

    sample_organisation.services.append(sample_service)
    db.session.commit()

    assert sample_organisation.name == 'sample organisation'

    dao_update_organisation(sample_organisation.id, name='updated org name')

    assert sample_organisation.name == 'updated org name'

    assert sample_organisation.organisation_type == 'central'
    assert sample_service.organisation_type == 'local'

    assert sample_organisation.email_branding == email_branding
    assert sample_service.email_branding is None

    assert sample_organisation.letter_branding == letter_branding
    assert sample_service.letter_branding is None


def test_update_organisation_updates_the_service_org_type_if_org_type_is_provided(
    sample_service,
    sample_organisation,
):
    sample_service.organisation_type = 'local'
    sample_organisation.organisation_type = 'local'

    sample_organisation.services.append(sample_service)
    db.session.commit()

    dao_update_organisation(sample_organisation.id, organisation_type='central')

    assert sample_organisation.organisation_type == 'central'
    assert sample_service.organisation_type == 'central'
    assert Service.get_history_model().query.filter_by(
        id=sample_service.id,
        version=2
    ).one().organisation_type == 'central'


def test_update_organisation_updates_the_service_branding_if_branding_is_provided(
    sample_service,
    sample_organisation,
):
    email_branding = create_email_branding()
    letter_branding = create_letter_branding()

    sample_organisation.services.append(sample_service)
    db.session.commit()

    dao_update_organisation(sample_organisation.id, email_branding_id=email_branding.id)
    dao_update_organisation(sample_organisation.id, letter_branding_id=letter_branding.id)

    assert sample_organisation.email_branding == email_branding
    assert sample_organisation.letter_branding == letter_branding
    assert sample_service.email_branding == email_branding
    assert sample_service.letter_branding == letter_branding


def test_update_organisation_does_not_override_service_branding(
    sample_service,
    sample_organisation,
):
    email_branding = create_email_branding()
    custom_email_branding = create_email_branding(name='custom')
    letter_branding = create_letter_branding()
    custom_letter_branding = create_letter_branding(name='custom', filename='custom')

    sample_service.email_branding = custom_email_branding
    sample_service.letter_branding = custom_letter_branding

    sample_organisation.services.append(sample_service)
    db.session.commit()

    dao_update_organisation(sample_organisation.id, email_branding_id=email_branding.id)
    dao_update_organisation(sample_organisation.id, letter_branding_id=letter_branding.id)

    assert sample_organisation.email_branding == email_branding
    assert sample_organisation.letter_branding == letter_branding
    assert sample_service.email_branding == custom_email_branding
    assert sample_service.letter_branding == custom_letter_branding


def test_update_organisation_updates_services_with_new_crown_type(
    sample_service,
    sample_organisation
):
    sample_organisation.services.append(sample_service)
    db.session.commit()

    assert Service.query.get(sample_service.id).crown

    dao_update_organisation(sample_organisation.id, crown=False)

    assert not Service.query.get(sample_service.id).crown


def test_add_service_to_organisation(sample_service, sample_organisation):
    assert sample_organisation.services == []

    sample_service.organisation_type = "central"
    sample_organisation.organisation_type = "local"
    sample_organisation.crown = False

    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    assert len(sample_organisation.services) == 1
    assert sample_organisation.services[0].id == sample_service.id

    assert sample_service.organisation_type == sample_organisation.organisation_type
    assert sample_service.crown == sample_organisation.crown
    assert Service.get_history_model().query.filter_by(
        id=sample_service.id,
        version=2
    ).one().organisation_type == sample_organisation.organisation_type
    assert sample_service.organisation_id == sample_organisation.id


def test_get_organisation_services(sample_service, sample_organisation):
    another_service = create_service(service_name='service 2')
    another_org = create_organisation()

    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    dao_add_service_to_organisation(another_service, sample_organisation.id)

    org_services = dao_get_organisation_services(sample_organisation.id)
    other_org_services = dao_get_organisation_services(another_org.id)

    assert [sample_service.name, another_service.name] == sorted([s.name for s in org_services])
    assert not other_org_services


def test_get_organisation_by_service_id(sample_service, sample_organisation):
    another_service = create_service(service_name='service 2')
    another_org = create_organisation()

    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    dao_add_service_to_organisation(another_service, another_org.id)

    organisation_1 = dao_get_organisation_by_service_id(sample_service.id)
    organisation_2 = dao_get_organisation_by_service_id(another_service.id)

    assert organisation_1 == sample_organisation
    assert organisation_2 == another_org


def test_dao_get_invited_organisation_user(sample_invited_org_user):
    invited_org_user = dao_get_invited_organisation_user(sample_invited_org_user.id)
    assert invited_org_user == sample_invited_org_user


def test_dao_get_invited_organisation_user_returns_none(notify_db):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_get_invited_organisation_user(uuid.uuid4())


def test_dao_get_users_for_organisation(sample_organisation):
    first = create_user(email='first@invited.com')
    second = create_user(email='another@invited.com')

    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=first.id)
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=second.id)

    results = dao_get_users_for_organisation(organisation_id=sample_organisation.id)

    assert len(results) == 2
    assert results[0] == first
    assert results[1] == second


def test_dao_get_users_for_organisation_returns_empty_list(sample_organisation):
    results = dao_get_users_for_organisation(organisation_id=sample_organisation.id)
    assert len(results) == 0


def test_dao_get_users_for_organisation_only_returns_active_users(sample_organisation):
    first = create_user(email='first@invited.com')
    second = create_user(email='another@invited.com')

    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=first.id)
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=second.id)

    second.state = 'inactive'

    results = dao_get_users_for_organisation(organisation_id=sample_organisation.id)
    assert len(results) == 1
    assert results[0] == first


def test_add_user_to_organisation_returns_user(sample_organisation):
    org_user = create_user()
    assert not org_user.organisations

    added_user = dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=org_user.id)
    assert len(added_user.organisations) == 1
    assert added_user.organisations[0] == sample_organisation


def test_add_user_to_organisation_when_user_does_not_exist(sample_organisation):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=uuid.uuid4())


def test_add_user_to_organisation_when_organisation_does_not_exist(sample_user):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_add_user_to_organisation(organisation_id=uuid.uuid4(), user_id=sample_user.id)


@pytest.mark.parametrize('domain, expected_org', (
    ('unknown.gov.uk', False),
    ('example.gov.uk', True),
))
def test_get_organisation_by_email_address(
    domain,
    expected_org,
    notify_db_session
):

    org = create_organisation()
    create_domain('example.gov.uk', org.id)
    create_domain('test.gov.uk', org.id)

    another_org = create_organisation(name='Another')
    create_domain('cabinet-office.gov.uk', another_org.id)
    create_domain('cabinetoffice.gov.uk', another_org.id)

    found_org = dao_get_organisation_by_email_address('test@{}'.format(domain))

    if expected_org:
        assert found_org is org
    else:
        assert found_org is None


def test_get_organisation_by_email_address_ignores_gsi_gov_uk(notify_db_session):
    org = create_organisation()
    create_domain('example.gov.uk', org.id)

    found_org = dao_get_organisation_by_email_address('test_gsi_address@example.gsi.gov.uk')
    assert org == found_org
