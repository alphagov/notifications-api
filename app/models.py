from . import db


def filter_null_value_fields(obj):
    return dict(
        filter(lambda x: x[1] is not None, obj.items())
    )


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email_address = db.Column(db.String(255), nullable=False, index=True, unique=True)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True)

    # def serialize(self):
    #     serialized = {
    #         'id': self.id,
    #         'name': self.name,
    #         'emailAddress': self.email_address,
    #         'locked': self.failed_login_count > current_app.config['MAX_FAILED_LOGIN_COUNT'],
    #         'createdAt': self.created_at.strftime(DATETIME_FORMAT),
    #         'updatedAt': self.updated_at.strftime(DATETIME_FORMAT),
    #         'role': self.role,
    #         'passwordChangedAt': self.password_changed_at.strftime(DATETIME_FORMAT),
    #         'failedLoginCount': self.failed_login_count
    #     }
    #     return filter_null_value_fields(serialized)


user_to_service = db.Table(
    'user_to_service',
    db.Model.metadata,
    db.Column('user_id', db.Integer, db.ForeignKey('users.id')),
    db.Column('service_id', db.Integer, db.ForeignKey('services.id'))
)


class Service(db.Model):
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False)
    active = db.Column(db.Boolean, index=False, unique=False, nullable=False)
    limit = db.Column(db.BigInteger, index=False, unique=False, nullable=False)
    users = db.relationship('User', secondary=user_to_service, backref=db.backref('user_to_service', lazy='dynamic'))
    restricted = db.Column(db.Boolean, index=False, unique=False, nullable=False)

    # def serialize(self):
    #     serialized = {
    #         'id': self.id,
    #         'name': self.name,
    #         'createdAt': self.created_at.strftime(DATETIME_FORMAT),
    #         'active': self.active,
    #         'restricted': self.restricted,
    #         'limit': self.limit,
    #         'user': self.users.serialize()
    #     }

    #     return filter_null_value_fields(serialized)
