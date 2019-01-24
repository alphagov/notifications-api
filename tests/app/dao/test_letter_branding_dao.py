from app.dao.letter_branding_dao import (
    dao_get_letter_branding_or_platform_default,
    dao_get_all_letter_branding,
    dao_create_letter_branding,
    dao_update_letter_branding
)
from app.models import LetterBranding
from tests.app.db import create_letter_branding


def test_dao_get_letter_branding_or_platform_default_returns_platform_default_if_domain_is_none(notify_db_session):
    create_letter_branding()
    result = dao_get_letter_branding_or_platform_default(domain=None)
    assert result.filename == 'hm-government'


def test_dao_get_letter_branding_or_platform_default_if_domain_is_not_associated_with_a_brand(notify_db_session):
    create_letter_branding()
    result = dao_get_letter_branding_or_platform_default(domain="foo.bar")
    assert result.filename == 'hm-government'


def test_dao_get_letter_branding_or_platform_default_returns_correct_brand_for_domain(notify_db_session):
    create_letter_branding()
    test_domain_branding = create_letter_branding(
        name='test domain', filename='test-domain', domain='test.domain', platform_default=False
    )
    result = dao_get_letter_branding_or_platform_default(domain='test.domain')
    result == test_domain_branding


def test_dao_get_all_letter_branding(notify_db_session):
    platform_default = create_letter_branding()
    test_domain = create_letter_branding(
        name='test domain', filename='test-domain', domain='test.domain', platform_default=False
    )

    results = dao_get_all_letter_branding()

    assert platform_default in results
    assert test_domain in results
    assert len(results) == 2


def test_dao_get_all_letter_branding_returns_empty_list_if_no_brands_exist(notify_db):
    assert dao_get_all_letter_branding() == []


def test_dao_create_letter_branding(notify_db_session):
    data = {
        'name': 'test-logo',
        'domain': 'test.co.uk',
        'filename': 'test-logo'
    }
    assert LetterBranding.query.count() == 0
    dao_create_letter_branding(LetterBranding(**data))

    assert LetterBranding.query.count() == 1

    new_letter_branding = LetterBranding.query.first()
    assert new_letter_branding.name == data['name']
    assert new_letter_branding.domain == data['domain']
    assert new_letter_branding.filename == data['name']
    assert not new_letter_branding.platform_default


def test_dao_update_letter_branding(notify_db_session):
    create_letter_branding(name='original')
    letter_branding = LetterBranding.query.first()
    assert letter_branding.name == 'original'
    dao_update_letter_branding(letter_branding.id, name='new name')
    assert LetterBranding.query.first().name == 'new name'
