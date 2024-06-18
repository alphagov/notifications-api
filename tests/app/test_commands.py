from app.commands import insert_inbound_numbers_from_file
from app.dao.inbound_numbers_dao import dao_get_available_inbound_numbers


def test_insert_inbound_numbers_from_file(notify_db_session, notify_api, tmpdir):
    numbers_file = tmpdir.join("numbers.txt")
    numbers_file.write("07700900373\n07700900473\n07700900375\n\n\n\n")

    notify_api.test_cli_runner().invoke(insert_inbound_numbers_from_file, ["-f", numbers_file])

    inbound_numbers = dao_get_available_inbound_numbers()
    assert len(inbound_numbers) == 3
    assert {x.number for x in inbound_numbers} == {"07700900373", "07700900473", "07700900375"}
