from app import db


def dao_create_event(event):
    db.session.add(event)
    db.session.commit()
