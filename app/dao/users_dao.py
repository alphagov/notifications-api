from datetime import datetime

from sqlalchemy.orm import load_only

from app import db
from app.models import User


def create_model_user(usr):
    db.session.add(usr)
    db.session.commit()


def get_model_users(user_id=None):
    if user_id:
        return User.query.filter_by(id=user_id).one()
    return User.query.filter_by().all()
