import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.dao.letter_branding_dao import (
    dao_get_all_letter_branding,
    dao_create_letter_branding,
    dao_update_letter_branding,
    dao_get_letter_branding_by_id
)
from app.models import LetterBranding
from tests.app.db import create_letter_branding


def test_dao_get_letter_branding_by_id(notify_db_session):
    letter_branding = create_letter_branding()
    result = dao_get_letter_branding_by_id(letter_branding.id)

    assert result == letter_branding


def test_dao_get_letter_brand_by_id_raises_exception_if_does_not_exist(notify_db_session):
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_get_letter_branding_by_id(uuid.uuid4())


def test_dao_get_all_letter_branding(notify_db_session):
    hm_gov = create_letter_branding()
    test_branding = create_letter_branding(
        name='test branding', filename='test-branding',
    )

    results = dao_get_all_letter_branding()

    assert hm_gov in results
    assert test_branding in results
    assert len(results) == 2


def test_dao_get_all_letter_branding_returns_empty_list_if_no_brands_exist(notify_db):
    assert dao_get_all_letter_branding() == []


def test_dao_create_letter_branding(notify_db_session):
    data = {
        'name': 'test-logo',
        'filename': 'test-logo'
    }
    assert LetterBranding.query.count() == 0
    dao_create_letter_branding(LetterBranding(**data))

    assert LetterBranding.query.count() == 1

    new_letter_branding = LetterBranding.query.first()
    assert new_letter_branding.name == data['name']
    assert new_letter_branding.filename == data['name']


def test_dao_update_letter_branding(notify_db_session):
    create_letter_branding(name='original')
    letter_branding = LetterBranding.query.first()
    assert letter_branding.name == 'original'
    dao_update_letter_branding(letter_branding.id, name='new name')
    assert LetterBranding.query.first().name == 'new name'
