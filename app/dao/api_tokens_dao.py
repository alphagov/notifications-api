from app import db
from app.models import ApiToken


def save_token_model(token, update_dict={}):
    if update_dict:
        del update_dict['id']
        db.session.query(ApiToken).filter_by(id=token.id).update(update_dict)
    else:
        db.session.add(token)
    db.session.commit()


def get_model_api_tokens(token=None):
    if token:
        return ApiToken.query.filter_by(token=token).one()
    return ApiToken.query.filter_by().all()
