from flask import current_app
from itsdangerous import URLSafeSerializer

from app import db
from app.models import Token


def save_model_token(token, update_dict={}):
    if update_dict:
        del update_dict['id']
        db.session.query(Token).filter_by(id=token.id).update(update_dict)
    else:
        token.token = _generate_token()
        db.session.add(token)
    db.session.commit()


def get_model_tokens(service_id=None, raise_=True):
    """
    :param raise_: when True query tokens using one() which will raise NoResultFound exception
                   when False query tokens usong first() which will return None and not raise an exception.
    """
    if service_id:
        # If expiry date is None the token is active
        if raise_:
            return Token.query.filter_by(service_id=service_id, expiry_date=None).one()
        else:
            return Token.query.filter_by(service_id=service_id, expiry_date=None).first()
    return Token.query.filter_by().all()


def get_unsigned_token(service_id):
    """
    There should only be one valid token for each service.
    This method can only be exposed to the Authentication of the api calls.
    """
    token = Token.query.filter_by(service_id=service_id, expiry_date=None).one()
    return _get_token(token.token)


def _generate_token(token=None):
    import uuid
    if not token:
        token = uuid.uuid4()
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))
    return serializer.dumps(str(token), current_app.config.get('DANGEROUS_SALT'))


def _get_token(token):
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))
    return serializer.loads(token, salt=current_app.config.get('DANGEROUS_SALT'))
