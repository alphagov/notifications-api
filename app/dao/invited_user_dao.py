from app import db


def save_invited_user(invited_user):
    db.session.add(invited_user)
    db.session.commit()
