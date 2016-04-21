import uuid
from flask import current_app
from itsdangerous import URLSafeSerializer

from app import db
from app.models import ApiKey

from app.dao.dao_utils import (
    transactional,
    version_class
)


@transactional
@version_class(ApiKey)
def save_model_api_key(api_key, update_dict={}):
    if update_dict:
        update_dict.pop('id', None)
        for key, value in update_dict.items():
            setattr(api_key, key, value)
        db.session.add(api_key)
    else:
        if not api_key.id:
            api_key.id = uuid.uuid4()  # must be set now so version history model can use same id
        api_key.secret = _generate_secret()
        db.session.add(api_key)


def get_model_api_keys(service_id, id=None):
    if id:
        return ApiKey.query.filter_by(id=id, service_id=service_id, expiry_date=None).one()
    return ApiKey.query.filter_by(service_id=service_id).all()


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
