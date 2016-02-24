from app import db

from app.dao.utils import create_secret_code


def save_invited_user(invited_user):
    invited_user.token = create_secret_code()
    db.session.add(invited_user)
    db.session.commit()
