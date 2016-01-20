from flask import current_app
from itsdangerous import URLSafeSerializer

from app import db
from app.models import ApiKey


def save_model_api_key(api_key, update_dict={}):
    if update_dict:
        if update_dict['id']:
            del update_dict['id']
        db.session.query(ApiKey).filter_by(id=api_key.id).update(update_dict)
    else:
        api_key.secret = _generate_secret()
        db.session.add(api_key)
    db.session.commit()


def get_model_api_keys(service_id=None, raise_=True):
    """
    :param raise_: when True query api_keys using one() which will raise NoResultFound exception
                   when False query api_keys usong first() which will return None and not raise an exception.
    """
    if service_id:
        # If expiry date is None the api_key is active
        if raise_:
            return ApiKey.query.filter_by(service_id=service_id, expiry_date=None).one()
        else:
            return ApiKey.query.filter_by(service_id=service_id, expiry_date=None).first()
    return ApiKey.query.filter_by().all()


def get_unsigned_secrets(service_id):
    """
    This method can only be exposed to the Authentication of the api calls.
    """
    api_keys = ApiKey.query.filter_by(service_id=service_id, expiry_date=None).all()
    keys = [_get_secret(x.secret) for x in api_keys]
    return keys


def get_unsigned_secret(key_id):
    """
    This method can only be exposed to the Authentication of the api calls.
    """
    api_key = ApiKey.query.filter_by(id=key_id, expiry_date=None).one()
    return _get_secret(api_key.secret)


def _generate_secret(token=None):
    import uuid
    if not token:
        token = uuid.uuid4()
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))
    return serializer.dumps(str(token), current_app.config.get('DANGEROUS_SALT'))


def _get_secret(signed_secret):
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))
    return serializer.loads(signed_secret, salt=current_app.config.get('DANGEROUS_SALT'))
