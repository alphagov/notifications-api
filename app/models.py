import uuid
import datetime

from sqlalchemy.dialects.postgresql import (
    UUID,
    JSON
)

from sqlalchemy import UniqueConstraint

from app.encryption import (
    hashpw,
    check_hash
)

from app import db

from app.history_meta import Versioned


def filter_null_value_fields(obj):
    return dict(
        filter(lambda x: x[1] is not None, obj.items())
    )


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String, nullable=False, index=True, unique=False)
    email_address = db.Column(db.String(255), nullable=False, index=True, unique=True)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.utcnow)
    _password = db.Column(db.String, index=False, unique=False, nullable=False)
    mobile_number = db.Column(db.String, index=False, unique=False, nullable=False)
    password_changed_at = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    logged_in_at = db.Column(db.DateTime, nullable=True)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    state = db.Column(db.String, nullable=False, default='pending')
    platform_admin = db.Column(db.Boolean, nullable=False, default=False)

    @property
    def password(self):
        raise AttributeError("Password not readable")

    @password.setter
    def password(self, password):
        self._password = hashpw(password)

    def check_password(self, password):
        return check_hash(password, self._password)


user_to_service = db.Table(
    'user_to_service',
    db.Model.metadata,
    db.Column('user_id', UUID(as_uuid=True), db.ForeignKey('users.id')),
    db.Column('service_id', UUID(as_uuid=True), db.ForeignKey('services.id')),
    UniqueConstraint('user_id', 'service_id', name='uix_user_to_service')
)


class Service(db.Model, Versioned):
    __tablename__ = 'services'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.utcnow)
    active = db.Column(db.Boolean, index=False, unique=False, nullable=False)
    message_limit = db.Column(db.BigInteger, index=False, unique=False, nullable=False)
    users = db.relationship(
        'User',
        secondary=user_to_service,
        backref=db.backref('user_to_service', lazy='dynamic'))
    restricted = db.Column(db.Boolean, index=False, unique=False, nullable=False)
    email_from = db.Column(db.Text, index=False, unique=True, nullable=False)
    created_by = db.relationship('User')
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)


class ApiKey(db.Model, Versioned):
    __tablename__ = 'api_keys'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    secret = db.Column(db.String(255), unique=True, nullable=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref=db.backref('api_keys', lazy='dynamic'))
    expiry_date = db.Column(db.DateTime)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.utcnow)
    created_by = db.relationship('User')
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)

    __table_args__ = (
        UniqueConstraint('service_id', 'name', name='uix_service_to_key_name'),
    )


class NotificationStatistics(db.Model):
    __tablename__ = 'notification_statistics'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day = db.Column(db.Date, index=True, nullable=False, unique=False, default=datetime.date.today)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref=db.backref('service_notification_stats', lazy='dynamic'))
    emails_requested = db.Column(db.BigInteger, index=False, unique=False, nullable=False, default=0)
    emails_delivered = db.Column(db.BigInteger, index=False, unique=False, nullable=False, default=0)
    emails_failed = db.Column(db.BigInteger, index=False, unique=False, nullable=False, default=0)
    sms_requested = db.Column(db.BigInteger, index=False, unique=False, nullable=False, default=0)
    sms_delivered = db.Column(db.BigInteger, index=False, unique=False, nullable=False, default=0)
    sms_failed = db.Column(db.BigInteger, index=False, unique=False, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint('service_id', 'day', name='uix_service_to_day'),
    )


TEMPLATE_TYPE_SMS = 'sms'
TEMPLATE_TYPE_EMAIL = 'email'
TEMPLATE_TYPE_LETTER = 'letter'

TEMPLATE_TYPES = [TEMPLATE_TYPE_SMS, TEMPLATE_TYPE_EMAIL, TEMPLATE_TYPE_LETTER]


class Template(db.Model, Versioned):
    __tablename__ = 'templates'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    template_type = db.Column(db.Enum(*TEMPLATE_TYPES, name='template_type'), nullable=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.utcnow)
    content = db.Column(db.Text, index=False, unique=False, nullable=False)
    archived = db.Column(db.Boolean, index=False, nullable=False, default=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False, nullable=False)
    service = db.relationship('Service', backref=db.backref('templates', lazy='dynamic'))
    subject = db.Column(db.Text, index=False, unique=True, nullable=True)
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    created_by = db.relationship('User')


MMG_PROVIDER = "mmg"
TWILIO_PROVIDER = "twilio"
FIRETEXT_PROVIDER = "firetext"
SES_PROVIDER = 'ses'

SMS_PROVIDERS = [MMG_PROVIDER, TWILIO_PROVIDER, FIRETEXT_PROVIDER]
EMAIL_PROVIDERS = [SES_PROVIDER]
PROVIDERS = SMS_PROVIDERS + EMAIL_PROVIDERS

NOTIFICATION_TYPE = ['email', 'sms', 'letter']


class ProviderStatistics(db.Model):
    __tablename__ = 'provider_statistics'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day = db.Column(db.Date, nullable=False)
    provider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provider_details.id'), index=True, nullable=False)
    provider_stats_to_provider = db.relationship(
        'ProviderDetails', backref=db.backref('provider_stats', lazy='dynamic')
    )
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref=db.backref('service_provider_stats', lazy='dynamic'))
    unit_count = db.Column(db.BigInteger, nullable=False)


class ProviderRates(db.Model):
    __tablename__ = 'provider_rates'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    valid_from = db.Column(db.DateTime, nullable=False)
    rate = db.Column(db.Numeric(), nullable=False)
    provider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provider_details.id'), index=True, nullable=False)
    provider_rate_to_provider = db.relationship('ProviderDetails', backref=db.backref('provider_rates', lazy='dynamic'))


class ProviderDetails(db.Model):
    __tablename__ = 'provider_details'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name = db.Column(db.String, nullable=False)
    identifier = db.Column(db.String, nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    notification_type = db.Column(db.Enum(*NOTIFICATION_TYPE, name='notification_type'), nullable=False)
    active = db.Column(db.Boolean, default=False)


JOB_STATUS_TYPES = ['pending', 'in progress', 'finished', 'sending limits exceeded']


class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    original_file_name = db.Column(db.String, nullable=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False, nullable=False)
    service = db.relationship('Service', backref=db.backref('jobs', lazy='dynamic'))
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), index=True, unique=False)
    template = db.relationship('Template', backref=db.backref('jobs', lazy='dynamic'))
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.utcnow)
    status = db.Column(db.Enum(*JOB_STATUS_TYPES, name='job_status_types'), nullable=False, default='pending')
    notification_count = db.Column(db.Integer, nullable=False)
    notifications_sent = db.Column(db.Integer, nullable=False, default=0)
    processing_started = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True)
    processing_finished = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True)
    created_by = db.relationship('User')
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)


VERIFY_CODE_TYPES = ['email', 'sms']


class VerifyCode(db.Model):
    __tablename__ = 'verify_codes'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    user = db.relationship('User', backref=db.backref('verify_codes', lazy='dynamic'))
    _code = db.Column(db.String, nullable=False)
    code_type = db.Column(db.Enum(*VERIFY_CODE_TYPES, name='verify_code_types'),
                          index=False, unique=False, nullable=False)
    expiry_datetime = db.Column(db.DateTime, nullable=False)
    code_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)

    @property
    def code(self):
        raise AttributeError("Code not readable")

    @code.setter
    def code(self, cde):
        self._code = hashpw(cde)

    def check_code(self, cde):
        return check_hash(cde, self._code)


NOTIFICATION_STATUS_TYPES = ['sending', 'delivered', 'failed']


class Notification(db.Model):

    __tablename__ = 'notifications'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    to = db.Column(db.String, nullable=False)
    job_id = db.Column(UUID(as_uuid=True), db.ForeignKey('jobs.id'), index=True, unique=False)
    job = db.relationship('Job', backref=db.backref('notifications', lazy='dynamic'))
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service')
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), index=True, unique=False)
    template = db.relationship('Template')
    content_char_count = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False)
    sent_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True)
    sent_by = db.Column(db.String, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=datetime.datetime.utcnow)
    status = db.Column(
        db.Enum(*NOTIFICATION_STATUS_TYPES, name='notification_status_types'), nullable=False, default='sending')
    reference = db.Column(db.String, nullable=True, index=True)


INVITED_USER_STATUS_TYPES = ['pending', 'accepted', 'cancelled']


class InvitedUser(db.Model):

    __tablename__ = 'invited_users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_address = db.Column(db.String(255), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    from_user = db.relationship('User')
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service')
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)
    status = db.Column(
        db.Enum(*INVITED_USER_STATUS_TYPES, name='invited_users_status_types'), nullable=False, default='pending')
    permissions = db.Column(db.String, nullable=False)

    # would like to have used properties for this but haven't found a way to make them
    # play nice with marshmallow yet
    def get_permissions(self):
        return self.permissions.split(',')


# Service Permissions
MANAGE_USERS = 'manage_users'
MANAGE_TEMPLATES = 'manage_templates'
MANAGE_SETTINGS = 'manage_settings'
SEND_TEXTS = 'send_texts'
SEND_EMAILS = 'send_emails'
SEND_LETTERS = 'send_letters'
MANAGE_API_KEYS = 'manage_api_keys'
PLATFORM_ADMIN = 'platform_admin'
VIEW_ACTIVITY = 'view_activity'

# List of permissions
PERMISSION_LIST = [
    MANAGE_USERS,
    MANAGE_TEMPLATES,
    MANAGE_SETTINGS,
    SEND_TEXTS,
    SEND_EMAILS,
    SEND_LETTERS,
    MANAGE_API_KEYS,
    PLATFORM_ADMIN,
    VIEW_ACTIVITY]


class Permission(db.Model):
    __tablename__ = 'permissions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Service id is optional, if the service is omitted we will assume the permission is not service specific.
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False, nullable=True)
    service = db.relationship('Service')
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    user = db.relationship('User')
    permission = db.Column(
        db.Enum(*PERMISSION_LIST, name='permission_types'),
        index=False,
        unique=False,
        nullable=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('service_id', 'user_id', 'permission', name='uix_service_user_permission'),
    )


class TemplateStatistics(db.Model):

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False, nullable=False)
    service = db.relationship('Service', backref=db.backref('template_statistics', lazy='dynamic'))
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), index=True, nullable=False, unique=False)
    template = db.relationship('Template')
    usage_count = db.Column(db.BigInteger, index=False, unique=False, nullable=False, default=1)
    day = db.Column(db.Date, index=True, nullable=False, unique=False, default=datetime.date.today)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)


class Event(db.Model):

    __tablename__ = 'events'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=datetime.datetime.utcnow)
    data = db.Column(JSON, nullable=False)
