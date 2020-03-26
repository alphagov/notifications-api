from app.dao.service_contact_list_dao import dao_get_contact_lists
from tests.app.db import create_service_contact_list


def test_dao_get_contact_lists(notify_db_session):
    contact_list = create_service_contact_list()
    create_service_contact_list(
        service=contact_list.service,
        archived=True,
    )

    fetched_list = dao_get_contact_lists(contact_list.service_id)

    assert len(fetched_list) == 1
    assert fetched_list[0] == contact_list
