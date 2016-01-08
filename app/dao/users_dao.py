from datetime import datetime

from sqlalchemy.orm import load_only

from app import db
from app.models import User


def create_user(email_address):
    user = User(email_address=email_address,
                created_at=datetime.now())
    db.session.add(user)
    db.session.commit()
    return user.id


def get_users(user_id=None):
    if user_id:
        return User.query.filter_by(id=user_id).one()
    return User.query.filter_by().all()
