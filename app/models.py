import uuid
import datetime
from flask import url_for

from sqlalchemy.dialects.postgresql import (
    UUID,
    JSON
)
from sqlalchemy import UniqueConstraint, and_
from sqlalchemy.orm import foreign, remote
from notifications_utils.recipients import (
    validate_email_address,
    validate_phone_number,
    InvalidPhoneError,
    InvalidEmailError
)

from app.encryption import (
    hashpw,
    check_hash
)
from app.authentication.utils import get_secret
from app import (
    db,
    encryption,
    DATETIME_FORMAT
)

from app.history_meta import Versioned


def filter_null_value_fields(obj):
    return dict(
        filter(lambda x: x[1] is not None, obj.items())
    )


class HistoryModel:
    @classmethod
    def from_original(cls, original):
        history = cls()
        history.update_from_original(original)
        return history

    def update_from_original(self, original):
        for c in self.__table__.columns:
            setattr(self, c.name, getattr(original, c.name))


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
    password_changed_at = db.Column(db.DateTime, index=False, unique=False, nullable=False,
                                    default=datetime.datetime.utcnow)
    logged_in_at = db.Column(db.DateTime, nullable=True)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    state = db.Column(db.String, nullable=False, default='pending')
    platform_admin = db.Column(db.Boolean, nullable=False, default=False)
    current_session_id = db.Column(UUID(as_uuid=True), nullable=True)

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

BRANDING_GOVUK = 'govuk'
BRANDING_ORG = 'org'
BRANDING_BOTH = 'both'


class BrandingTypes(db.Model):
    __tablename__ = 'branding_type'
    name = db.Column(db.String(255), primary_key=True)


class Organisation(db.Model):
    __tablename__ = 'organisation'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    colour = db.Column(db.String(7), nullable=True)
    logo = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(255), nullable=True)


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
    active = db.Column(db.Boolean, index=False, unique=False, nullable=False, default=True)
    message_limit = db.Column(db.BigInteger, index=False, unique=False, nullable=False)
    users = db.relationship(
        'User',
        secondary=user_to_service,
        backref=db.backref('user_to_service', lazy='dynamic'))
    restricted = db.Column(db.Boolean, index=False, unique=False, nullable=False)
    research_mode = db.Column(db.Boolean, index=False, unique=False, nullable=False, default=False)
    can_send_letters = db.Column(db.Boolean, nullable=False, default=False)
    email_from = db.Column(db.Text, index=False, unique=True, nullable=False)
    created_by = db.relationship('User')
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    reply_to_email_address = db.Column(db.Text, index=False, unique=False, nullable=True)
    letter_contact_block = db.Column(db.Text, index=False, unique=False, nullable=True)
    sms_sender = db.Column(db.String(11), nullable=True)
    organisation_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organisation.id'), index=True, nullable=True)
    organisation = db.relationship('Organisation')
    branding = db.Column(
        db.String(255),
        db.ForeignKey('branding_type.name'),
        index=True,
        nullable=False,
        default=BRANDING_GOVUK
    )


MOBILE_TYPE = 'mobile'
EMAIL_TYPE = 'email'

WHITELIST_RECIPIENT_TYPE = [MOBILE_TYPE, EMAIL_TYPE]
whitelist_recipient_types = db.Enum(*WHITELIST_RECIPIENT_TYPE, name='recipient_type')


class ServiceWhitelist(db.Model):
    __tablename__ = 'service_whitelist'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref='whitelist')
    recipient_type = db.Column(whitelist_recipient_types, nullable=False)
    recipient = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    @classmethod
    def from_string(cls, service_id, recipient_type, recipient):
        instance = cls(service_id=service_id, recipient_type=recipient_type)

        try:
            if recipient_type == MOBILE_TYPE:
                validate_phone_number(recipient)
                instance.recipient = recipient
            elif recipient_type == EMAIL_TYPE:
                validate_email_address(recipient)
                instance.recipient = recipient
            else:
                raise ValueError('Invalid recipient type')
        except InvalidPhoneError:
            raise ValueError('Invalid whitelist: "{}"'.format(recipient))
        except InvalidEmailError:
            raise ValueError('Invalid whitelist: "{}"'.format(recipient))
        else:
            return instance

    def __repr__(self):
        return 'Recipient {} of type: {}'.format(self.recipient, self.recipient_type)


class ApiKey(db.Model, Versioned):
    __tablename__ = 'api_keys'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    secret = db.Column(db.String(255), unique=True, nullable=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref='api_keys')
    key_type = db.Column(db.String(255), db.ForeignKey('key_types.name'), index=True, nullable=False)
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

    @property
    def unsigned_secret(self):
        return get_secret(self.secret)


KEY_TYPE_NORMAL = 'normal'
KEY_TYPE_TEAM = 'team'
KEY_TYPE_TEST = 'test'


class KeyTypes(db.Model):
    __tablename__ = 'key_types'

    name = db.Column(db.String(255), primary_key=True)


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


class TemplateProcessTypes(db.Model):
    __tablename__ = 'template_process_type'
    name = db.Column(db.String(255), primary_key=True)


SMS_TYPE = 'sms'
EMAIL_TYPE = 'email'
LETTER_TYPE = 'letter'

TEMPLATE_TYPES = [SMS_TYPE, EMAIL_TYPE, LETTER_TYPE]

template_types = db.Enum(*TEMPLATE_TYPES, name='template_type')

NORMAL = 'normal'
PRIORITY = 'priority'
TEMPLATE_PROCESS_TYPE = [NORMAL, PRIORITY]


class Template(db.Model):
    __tablename__ = 'templates'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    template_type = db.Column(template_types, nullable=False)
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
    service = db.relationship('Service', backref='templates')
    subject = db.Column(db.Text, index=False, unique=False, nullable=True)
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    created_by = db.relationship('User')
    version = db.Column(db.Integer, default=1, nullable=False)
    process_type = db.Column(db.String(255),
                             db.ForeignKey('template_process_type.name'),
                             index=True,
                             nullable=False,
                             default=NORMAL)

    def get_link(self):
        # TODO: use "/v2/" route once available
        return url_for(
            "template.get_template_by_id_and_service_id",
            service_id=self.service_id,
            template_id=self.id,
            _external=True
        )

    def serialize(self):

        serialized = {
            "id": self.id,
            "type": self.template_type,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
            "created_by": self.created_by.email_address,
            "version": self.version,
            "body": self.content,
            "subject": self.subject if self.template_type == EMAIL_TYPE else None
        }

        return serialized


class TemplateHistory(db.Model):
    __tablename__ = 'templates_history'

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    template_type = db.Column(template_types, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime)
    content = db.Column(db.Text, nullable=False)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service')
    subject = db.Column(db.Text)
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    created_by = db.relationship('User')
    version = db.Column(db.Integer, primary_key=True, nullable=False)
    process_type = db.Column(db.String(255),
                             db.ForeignKey('template_process_type.name'),
                             index=True,
                             nullable=False,
                             default=NORMAL)

    def serialize(self):

        serialized = {
            "id": self.id,
            "type": self.template_type,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
            "created_by": self.created_by.email_address,
            "version": self.version,
            "body": self.content,
            "subject": self.subject if self.template_type == EMAIL_TYPE else None
        }

        return serialized


MMG_PROVIDER = "mmg"
FIRETEXT_PROVIDER = "firetext"
SES_PROVIDER = 'ses'

SMS_PROVIDERS = [MMG_PROVIDER, FIRETEXT_PROVIDER]
EMAIL_PROVIDERS = [SES_PROVIDER]
PROVIDERS = SMS_PROVIDERS + EMAIL_PROVIDERS

NOTIFICATION_TYPE = [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE]
notification_types = db.Enum(*NOTIFICATION_TYPE, name='notification_type')


class ProviderStatistics(db.Model):
    __tablename__ = 'provider_statistics'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day = db.Column(db.Date, nullable=False)
    provider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provider_details.id'), index=True, nullable=False)
    provider = db.relationship(
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
    provider = db.relationship('ProviderDetails', backref=db.backref('provider_rates', lazy='dynamic'))


class ProviderDetails(db.Model):
    __tablename__ = 'provider_details'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name = db.Column(db.String, nullable=False)
    identifier = db.Column(db.String, nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    notification_type = db.Column(notification_types, nullable=False)
    active = db.Column(db.Boolean, default=False, nullable=False)
    version = db.Column(db.Integer, default=1, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=True)
    created_by = db.relationship('User')


class ProviderDetailsHistory(db.Model, HistoryModel):
    __tablename__ = 'provider_details_history'

    id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    display_name = db.Column(db.String, nullable=False)
    identifier = db.Column(db.String, nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    notification_type = db.Column(notification_types, nullable=False)
    active = db.Column(db.Boolean, nullable=False)
    version = db.Column(db.Integer, primary_key=True, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=True)
    created_by = db.relationship('User')


JOB_STATUS_PENDING = 'pending'
JOB_STATUS_IN_PROGRESS = 'in progress'
JOB_STATUS_FINISHED = 'finished'
JOB_STATUS_SENDING_LIMITS_EXCEEDED = 'sending limits exceeded'
JOB_STATUS_SCHEDULED = 'scheduled'
JOB_STATUS_CANCELLED = 'cancelled'
JOB_STATUS_READY_TO_SEND = 'ready to send'
JOB_STATUS_SENT_TO_DVLA = 'sent to dvla'
JOB_STATUS_TYPES = [
    JOB_STATUS_PENDING,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_FINISHED,
    JOB_STATUS_SENDING_LIMITS_EXCEEDED,
    JOB_STATUS_SCHEDULED,
    JOB_STATUS_CANCELLED
]


class JobStatus(db.Model):
    __tablename__ = 'job_status'

    name = db.Column(db.String(255), primary_key=True)


class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    original_file_name = db.Column(db.String, nullable=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False, nullable=False)
    service = db.relationship('Service', backref=db.backref('jobs', lazy='dynamic'))
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), index=True, unique=False)
    template = db.relationship('Template', backref=db.backref('jobs', lazy='dynamic'))
    template_version = db.Column(db.Integer, nullable=False)
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
    notification_count = db.Column(db.Integer, nullable=False)
    notifications_sent = db.Column(db.Integer, nullable=False, default=0)
    notifications_delivered = db.Column(db.Integer, nullable=False, default=0)
    notifications_failed = db.Column(db.Integer, nullable=False, default=0)

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
    scheduled_for = db.Column(
        db.DateTime,
        index=True,
        unique=False,
        nullable=True)
    job_status = db.Column(
        db.String(255), db.ForeignKey('job_status.name'), index=True, nullable=False, default='pending'
    )


VERIFY_CODE_TYPES = [EMAIL_TYPE, SMS_TYPE]


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


NOTIFICATION_CREATED = 'created'
NOTIFICATION_SENDING = 'sending'
NOTIFICATION_DELIVERED = 'delivered'
NOTIFICATION_PENDING = 'pending'
NOTIFICATION_FAILED = 'failed'
NOTIFICATION_TECHNICAL_FAILURE = 'technical-failure'
NOTIFICATION_TEMPORARY_FAILURE = 'temporary-failure'
NOTIFICATION_PERMANENT_FAILURE = 'permanent-failure'

NOTIFICATION_STATUS_TYPES_FAILED = [
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
]

NOTIFICATION_STATUS_TYPES_COMPLETED = [
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
]

NOTIFICATION_STATUS_TYPES_BILLABLE = [
    NOTIFICATION_SENDING,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
]

NOTIFICATION_STATUS_TYPES = [
    NOTIFICATION_CREATED,
    NOTIFICATION_SENDING,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING,
    NOTIFICATION_FAILED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
]
NOTIFICATION_STATUS_TYPES_ENUM = db.Enum(*NOTIFICATION_STATUS_TYPES, name='notify_status_type')


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    to = db.Column(db.String, nullable=False)
    job_id = db.Column(UUID(as_uuid=True), db.ForeignKey('jobs.id'), index=True, unique=False)
    job = db.relationship('Job', backref=db.backref('notifications', lazy='dynamic'))
    job_row_number = db.Column(db.Integer, nullable=True)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service')
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), index=True, unique=False)
    template = db.relationship('Template')
    template_version = db.Column(db.Integer, nullable=False)
    api_key_id = db.Column(UUID(as_uuid=True), db.ForeignKey('api_keys.id'), index=True, unique=False)
    api_key = db.relationship('ApiKey')
    key_type = db.Column(db.String, db.ForeignKey('key_types.name'), index=True, unique=False, nullable=False)
    billable_units = db.Column(db.Integer, nullable=False, default=0)
    notification_type = db.Column(notification_types, index=True, nullable=False)
    created_at = db.Column(
        db.DateTime,
        index=True,
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
    status = db.Column(NOTIFICATION_STATUS_TYPES_ENUM, index=True, nullable=False, default='created')
    reference = db.Column(db.String, nullable=True, index=True)
    client_reference = db.Column(db.String, index=True, nullable=True)
    _personalisation = db.Column(db.String, nullable=True)

    template_history = db.relationship('TemplateHistory', primaryjoin=and_(
        foreign(template_id) == remote(TemplateHistory.id),
        foreign(template_version) == remote(TemplateHistory.version)
    ))

    @property
    def personalisation(self):
        if self._personalisation:
            return encryption.decrypt(self._personalisation)
        return None

    @personalisation.setter
    def personalisation(self, personalisation):
        if personalisation:
            self._personalisation = encryption.encrypt(personalisation)

    def completed_at(self):
        if self.status in NOTIFICATION_STATUS_TYPES_COMPLETED:
            return self.updated_at.strftime(DATETIME_FORMAT)

        return None

    @staticmethod
    def substitute_status(status_or_statuses):
        """
        static function that takes a status or list of statuses and substitutes our new failure types if it finds
        the deprecated one

        > IN
        'failed'

        < OUT
        ['technical-failure', 'temporary-failure', 'permanent-failure']

        -

        > IN
        ['failed', 'created']

        < OUT
        ['technical-failure', 'temporary-failure', 'permanent-failure', 'created']


        :param status_or_statuses: a single status or list of statuses
        :return: a single status or list with the current failure statuses substituted for 'failure'
        """

        def _substitute_status_str(_status):
            return NOTIFICATION_STATUS_TYPES_FAILED if _status == NOTIFICATION_FAILED else _status

        def _substitute_status_seq(_statuses):
            if NOTIFICATION_FAILED in _statuses:
                _statuses = list(set(
                    NOTIFICATION_STATUS_TYPES_FAILED + [_s for _s in _statuses if _s != NOTIFICATION_FAILED]
                ))
            return _statuses

        if isinstance(status_or_statuses, str):
            return _substitute_status_str(status_or_statuses)

        return _substitute_status_seq(status_or_statuses)

    @property
    def content(self):
        from app.utils import get_template_instance
        template_object = get_template_instance(self.template.__dict__, self.personalisation)
        return str(template_object)

    @property
    def subject(self):
        from app.utils import get_template_instance
        if self.notification_type == EMAIL_TYPE:
            template_object = get_template_instance(self.template.__dict__, self.personalisation)
            return template_object.subject

    def serialize(self):

        template_dict = {
            'version': self.template.version,
            'id': self.template.id,
            'uri': self.template.get_link()
        }

        serialized = {
            "id": self.id,
            "reference": self.client_reference,
            "email_address": self.to if self.notification_type == EMAIL_TYPE else None,
            "phone_number": self.to if self.notification_type == SMS_TYPE else None,
            "line_1": None,
            "line_2": None,
            "line_3": None,
            "line_4": None,
            "line_5": None,
            "line_6": None,
            "postcode": None,
            "type": self.notification_type,
            "status": self.status,
            "template": template_dict,
            "body": self.content,
            "subject": self.subject,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "sent_at": self.sent_at.strftime(DATETIME_FORMAT) if self.sent_at else None,
            "completed_at": self.completed_at()
        }

        return serialized


class NotificationHistory(db.Model, HistoryModel):
    __tablename__ = 'notification_history'

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    job_id = db.Column(UUID(as_uuid=True), db.ForeignKey('jobs.id'), index=True, unique=False)
    job = db.relationship('Job')
    job_row_number = db.Column(db.Integer, nullable=True)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service')
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), index=True, unique=False)
    template = db.relationship('Template')
    template_version = db.Column(db.Integer, nullable=False)
    api_key_id = db.Column(UUID(as_uuid=True), db.ForeignKey('api_keys.id'), index=True, unique=False)
    api_key = db.relationship('ApiKey')
    key_type = db.Column(db.String, db.ForeignKey('key_types.name'), index=True, unique=False, nullable=False)
    billable_units = db.Column(db.Integer, nullable=False, default=0)
    notification_type = db.Column(notification_types, index=True, nullable=False)
    created_at = db.Column(db.DateTime, index=True, unique=False, nullable=False)
    sent_at = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    sent_by = db.Column(db.String, nullable=True)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    status = db.Column(NOTIFICATION_STATUS_TYPES_ENUM, index=True, nullable=False, default='created')
    reference = db.Column(db.String, nullable=True, index=True)
    client_reference = db.Column(db.String, nullable=True)

    @classmethod
    def from_original(cls, notification):
        history = super().from_original(notification)
        return history


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
