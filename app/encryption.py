from flask.ext.bcrypt import generate_password_hash, check_password_hash

from itsdangerous import URLSafeSerializer


class Encryption:

    def init_app(self, app):
        self.serializer = URLSafeSerializer(app.config.get('SECRET_KEY'))
        self.salt = app.config.get('DANGEROUS_SALT')

    def encrypt(self, thing_to_encrypt):
        return self.serializer.dumps(thing_to_encrypt, self.salt)

    def decrypt(self, thing_to_decrypt):
        return self.serializer.loads(thing_to_decrypt, salt=self.salt)


def hashpw(password):
    return generate_password_hash(password.encode('UTF-8'), 10)


def check_hash(password, hashed_password):
    # If salt is invalid throws a 500 should add try/catch here
    return check_password_hash(hashed_password, password)
