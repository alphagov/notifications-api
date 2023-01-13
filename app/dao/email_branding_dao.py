from app import db
from app.dao.dao_utils import autocommit
from app.models import EmailBranding, Organisation, Service
from app.utils import get_archived_db_column_value


def dao_get_existing_alternate_email_branding_for_name(name):
    """
    Returns any email branding with name of format `{name} (alternate {x})`

    where name is the provided name and x is an integer starting at 1
    """
    return (
        EmailBranding.query.filter(EmailBranding.name.ilike(f"{name} (alternate %)")).order_by(EmailBranding.name).all()
    )


def dao_get_email_branding_options():
    return EmailBranding.query.filter_by(active=True).all()


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


@autocommit
def dao_archive_email_branding(email_branding_id):
    email_branding = dao_get_email_branding_by_id(email_branding_id)

    email_branding.active = False
    email_branding.name = get_archived_db_column_value(email_branding.name)
    db.session.add(email_branding)


def dao_get_orgs_and_services_associated_with_email_branding(email_branding_id):
    services = (
        db.session.query(
            Service.name,
            Service.id,
        )
        .select_from(Service)
        .join(Service.email_branding)
        .filter(Service.active == True, EmailBranding.id == email_branding_id)  # noqa
        .group_by(
            Service.id,
            Service.name,
        )
        .order_by(Service.name)
        .all()
    )

    organisations = (
        db.session.query(Organisation.name, Organisation.id)
        .select_from(Organisation)
        .filter(Organisation.active == True, Organisation.email_branding_id == email_branding_id)  # noqa
        .group_by(
            Organisation.id,
            Organisation.name,
        )
        .order_by(Organisation.name)
        .all()
    )

    return {"services": [s._asdict() for s in services], "organisations": [o._asdict() for o in organisations]}
