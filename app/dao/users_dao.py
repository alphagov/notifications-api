from datetime import datetime
from . import DAOException
from sqlalchemy.orm import load_only

from app import db
from app.models import User


def save_model_user(usr, update_dict={}):
    if update_dict:
        del update_dict['id']
        db.session.query(User).filter_by(id=usr.id).update(update_dict)
    else:
        db.session.add(usr)
    db.session.commit()


def delete_model_user(user):
    db.session.delete(user)
    db.session.commit()


def get_model_users(user_id=None):
    if user_id:
        return User.query.filter_by(id=user_id).one()
    return User.query.filter_by().all()
