import uuid

from app.models import ServiceWhitelist
from app.dao.service_whitelist_dao import (

    dao_fetch_service_whitelist,
    dao_add_and_commit_whitelisted_contacts,
    dao_remove_service_whitelist
)


def test_fetch_service_whitelist_gets_whitelists(sample_service_whitelist):
    whitelist = dao_fetch_service_whitelist(sample_service_whitelist.service_id)
    assert len(whitelist) == 1
    assert whitelist[0].id == sample_service_whitelist.id


def test_fetch_service_whitelist_ignores_other_service(sample_service_whitelist):
    assert len(dao_fetch_service_whitelist(uuid.uuid4())) == 0


def test_add_and_commit_whitelisted_contacts_saves_data(sample_service):
    whitelist = ServiceWhitelist.from_string(sample_service.id, 'foo@example.com')
    dao_add_and_commit_whitelisted_contacts([whitelist])

    db_contents = ServiceWhitelist.query.all()
    assert len(db_contents) == 1
    assert db_contents[0].id == whitelist.id
