from app import db
from app.dao.dao_utils import autocommit
from app.models import EmailBranding


def dao_get_existing_alternate_email_branding_for_name(name):
    """
    Returns any email branding with name of format `{name} (alternate {x})`

    where name is the provided name and x is an integer starting at 1
    """
    return (
        EmailBranding.query.filter(EmailBranding.name.ilike(f"{name} (alternate %)")).order_by(EmailBranding.name).all()
    )


def dao_get_email_branding_options():
    return EmailBranding.query.all()


def dao_get_email_branding_by_id(email_branding_id):
    return EmailBranding.query.filter_by(id=email_branding_id).one()


def dao_get_email_branding_by_name(email_branding_name):
    return EmailBranding.query.filter_by(name=email_branding_name).first()


def dao_get_email_branding_by_name_case_insensitive(email_branding_name):
    return EmailBranding.query.filter(EmailBranding.name.ilike(email_branding_name)).all()


@autocommit
def dao_create_email_branding(email_branding):
    db.session.add(email_branding)


@autocommit
def dao_update_email_branding(email_branding, **kwargs):
    for key, value in kwargs.items():
        setattr(email_branding, key, value or None)
    db.session.add(email_branding)
