from . import db
import datetime

from sqlalchemy.dialects.postgresql import UUID


def filter_null_value_fields(obj):
    return dict(
        filter(lambda x: x[1] is not None, obj.items())
    )


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email_address = db.Column(db.String(255), nullable=False, index=True, unique=True)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.now)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.now)


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
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.now)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.now)
    active = db.Column(db.Boolean, index=False, unique=False, nullable=False)
    limit = db.Column(db.BigInteger, index=False, unique=False, nullable=False)
    users = db.relationship(
        'User',
        secondary=user_to_service,
        backref=db.backref('user_to_service', lazy='dynamic'))
    restricted = db.Column(db.Boolean, index=False, unique=False, nullable=False)


class Token(db.Model):
    __tablename__ = 'tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(255), unique=True, nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref=db.backref('tokens', lazy='dynamic'))
    expiry_date = db.Column(db.DateTime)


TEMPLATE_TYPES = ['sms', 'email', 'letter']


class Template(db.Model):
    __tablename__ = 'templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    template_type = db.Column(db.Enum(*TEMPLATE_TYPES, name='template_type'), nullable=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.now)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.now)
    content = db.Column(db.Text, index=False, unique=False, nullable=False)
    service_id = db.Column(db.BigInteger, db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service', backref=db.backref('templates', lazy='dynamic'))


class Job(db.Model):

    __tablename__ = 'jobs'

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    original_file_name = db.Column(db.String, nullable=False)
    service_id = db.Column(db.BigInteger, db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service', backref=db.backref('jobs', lazy='dynamic'))
    template_id = db.Column(db.BigInteger, db.ForeignKey('templates.id'), index=True, unique=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.now)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.now)
