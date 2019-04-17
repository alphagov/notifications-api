from app import db
from app.dao.dao_utils import transactional
from app.models import LetterBranding


def dao_get_letter_branding_by_id(letter_branding_id):
    return LetterBranding.query.filter(LetterBranding.id == letter_branding_id).one()


def dao_get_letter_branding_by_name(letter_branding_name):
    return LetterBranding.query.filter_by(name=letter_branding_name).first()


def dao_get_all_letter_branding():
    return LetterBranding.query.order_by(LetterBranding.name).all()


@transactional
def dao_create_letter_branding(letter_branding):
    db.session.add(letter_branding)


@transactional
def dao_update_letter_branding(letter_branding_id, **kwargs):
    letter_branding = LetterBranding.query.get(letter_branding_id)
    for key, value in kwargs.items():
        setattr(letter_branding, key, value or None)
    db.session.add(letter_branding)
    return letter_branding
