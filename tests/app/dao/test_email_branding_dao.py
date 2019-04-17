from app.dao.email_branding_dao import (
    dao_get_email_branding_options,
    dao_get_email_branding_by_id,
    dao_get_email_branding_by_name,
    dao_update_email_branding,
)
from app.models import EmailBranding

from tests.app.db import create_email_branding


def test_get_email_branding_options_gets_all_email_branding(notify_db, notify_db_session):
    email_branding_1 = create_email_branding(name='test_email_branding_1')
    email_branding_2 = create_email_branding(name='test_email_branding_2')

    email_branding = dao_get_email_branding_options()

    assert len(email_branding) == 2
    assert email_branding_1 == email_branding[0]
    assert email_branding_2 == email_branding[1]


def test_get_email_branding_by_id_gets_correct_email_branding(notify_db, notify_db_session):
    email_branding = create_email_branding()

    email_branding_from_db = dao_get_email_branding_by_id(email_branding.id)

    assert email_branding_from_db == email_branding


def test_get_email_branding_by_name_gets_correct_email_branding(notify_db, notify_db_session):
    email_branding = create_email_branding(name="Crystal Gems")

    email_branding_from_db = dao_get_email_branding_by_name("Crystal Gems")

    assert email_branding_from_db == email_branding


def test_update_email_branding(notify_db, notify_db_session):
    updated_name = 'new name'
    create_email_branding()

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert email_branding[0].name != updated_name

    dao_update_email_branding(email_branding[0], name=updated_name)

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert email_branding[0].name == updated_name


def test_email_branding_has_no_domain(notify_db, notify_db_session):
    create_email_branding()
    email_branding = EmailBranding.query.all()
    assert not hasattr(email_branding, 'domain')
