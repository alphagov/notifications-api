
from app.models import InvitedUser

from app.dao.invited_user_dao import save_invited_user


def test_create_invited_user(notify_db, notify_db_session, sample_service):
    assert InvitedUser.query.count() == 0
    email_address = 'invited_user@service.gov.uk'
    invite_from = sample_service.users[0]

    data = {
        'service': sample_service,
        'email_address': email_address,
        'from_user': invite_from
    }

    invited_user = InvitedUser(**data)
    save_invited_user(invited_user)

    assert InvitedUser.query.count() == 1
    assert invited_user.email_address == email_address
    assert invited_user.from_user == invite_from
