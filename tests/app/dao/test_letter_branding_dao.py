from app.dao.letter_branding_dao import get_letter_branding_or_platform_default
from tests.app.db import create_letter_branding


def test_get_letter_branding_or_platform_default_returns_platform_default_if_domain_is_none(notify_db_session):
    create_letter_branding()
    result = get_letter_branding_or_platform_default(domain=None)
    assert result.filename == 'hm-government'


def test_get_letter_branding_or_platform_default_if_domain_is_not_associated_with_a_brand(notify_db_session):
    create_letter_branding()
    result = get_letter_branding_or_platform_default(domain="foo.bar")
    assert result.filename == 'hm-government'


def test_get_letter_branding_or_platform_default_returns_correct_brand_for_domain(notify_db_session):
    create_letter_branding()
    test_domain_branding = create_letter_branding(
        name='test domain', filename='test-domain', domain='test.domain', platform_default=False
    )
    result = get_letter_branding_or_platform_default(domain='test.domain')
    result == test_domain_branding
