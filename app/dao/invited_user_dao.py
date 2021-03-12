from datetime import datetime, timedelta

from app import db
from app.models import InvitedUser


def save_invited_user(invited_user):
    db.session.add(invited_user)
    db.session.commit()


def get_invited_user_by_service_and_id(service_id, invited_user_id):
    return InvitedUser.query.filter_by(service_id=service_id, id=invited_user_id).one()


def get_invited_user_by_id(invited_user_id):
    return InvitedUser.query.filter_by(id=invited_user_id).one()


def get_invited_users_for_service(service_id):
    return InvitedUser.query.filter_by(service_id=service_id).all()


def delete_invitations_created_more_than_two_days_ago():
    deleted = db.session.query(InvitedUser).filter(
        InvitedUser.created_at <= datetime.utcnow() - timedelta(days=2)
    ).delete()
    db.session.commit()
    return deleted
