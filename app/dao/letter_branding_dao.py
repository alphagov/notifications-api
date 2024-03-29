from app import db
from app.dao.dao_utils import autocommit
from app.models import LetterBranding, Organisation, Service


def dao_get_existing_alternate_letter_branding_for_name(name):
    """
    Returns any letter branding with name of format `{name} (alternate {x})`

    where name is the provided name and x is an integer starting at 1
    """
    return (
        LetterBranding.query.filter(LetterBranding.name.ilike(f"{name} (alternate %)"))
        .order_by(LetterBranding.name)
        .all()
    )


def dao_get_letter_branding_by_id(letter_branding_id):
    return LetterBranding.query.filter(LetterBranding.id == letter_branding_id).one()


def dao_get_letter_branding_by_name(letter_branding_name):
    return LetterBranding.query.filter_by(name=letter_branding_name).first()


def dao_get_letter_branding_by_name_case_insensitive(letter_branding_name):
    return LetterBranding.query.filter(LetterBranding.name.ilike(letter_branding_name)).all()


def dao_get_all_letter_branding():
    return LetterBranding.query.order_by(LetterBranding.name).all()


@autocommit
def dao_create_letter_branding(letter_branding):
    db.session.add(letter_branding)


@autocommit
def dao_update_letter_branding(letter_branding_id, **kwargs):
    letter_branding = LetterBranding.query.get(letter_branding_id)
    for key, value in kwargs.items():
        setattr(letter_branding, key, value or None)
    db.session.add(letter_branding)
    return letter_branding


def dao_get_orgs_and_services_associated_with_letter_branding(letter_branding_id):
    services = (
        db.session.query(
            Service.name,
            Service.id,
        )
        .select_from(Service)
        .join(Service.letter_branding)
        .filter(Service.active == True, LetterBranding.id == letter_branding_id)  # noqa
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
        .filter(Organisation.active == True, Organisation.letter_branding_id == letter_branding_id)  # noqa
        .group_by(
            Organisation.id,
            Organisation.name,
        )
        .order_by(Organisation.name)
        .all()
    )

    return {"services": [s._asdict() for s in services], "organisations": [o._asdict() for o in organisations]}
