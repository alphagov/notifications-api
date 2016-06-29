from flask import current_app
from itsdangerous import URLSafeSerializer


def get_secret(secret):
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))
    return serializer.loads(secret, salt=current_app.config.get('DANGEROUS_SALT'))


def generate_secret(token):
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))
    return serializer.dumps(str(token), current_app.config.get('DANGEROUS_SALT'))
