from app import db
from app.models import Token


def save_token_model(token, update_dict={}):
    if update_dict:
        del update_dict['id']
        db.session.query(Token).filter_by(id=token.id).update(update_dict)
    else:
        db.session.add(token)
    db.session.commit()


def get_model_tokens(service_id=None, raise_=True):
    if service_id:
        # If expiry date is None the token is active
        if raise_:
            return Token.query.filter_by(service_id=service_id, expiry_date=None).one()
        else:
            return Token.query.filter_by(service_id=service_id, expiry_date=None).first()
    return Token.query.filter_by().all()
