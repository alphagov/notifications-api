from app import db
from app.models import Token


def save_token_model(token, update_dict={}):
    if update_dict:
        del update_dict['id']
        db.session.query(Token).filter_by(id=token.id).update(update_dict)
    else:
        db.session.add(token)
    db.session.commit()


def get_model_tokens(service_id=None):
    if service_id:
        return Token.query.filter_by(service_id=service_id).one()
    return Token.query.filter_by().all()


def delete_model_token(token):
    db.session.delete(token)
    db.session.commit()
