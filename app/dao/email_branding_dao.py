from app import db
from app.dao.dao_utils import transactional
from app.models import EmailBranding


def dao_get_email_branding_options():
    return EmailBranding.query.all()


def dao_get_email_branding_by_id(email_branding_id):
    return EmailBranding.query.filter_by(id=email_branding_id).one()


def dao_get_email_branding_by_name(email_branding_name):
    return EmailBranding.query.filter_by(name=email_branding_name).one()


@transactional
def dao_create_email_branding(email_branding):
    db.session.add(email_branding)


@transactional
def dao_update_email_branding(email_branding, **kwargs):
    for key, value in kwargs.items():
        setattr(email_branding, key, value or None)
    db.session.add(email_branding)
