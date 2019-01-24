from app import db
from app.dao.dao_utils import transactional
from app.models import LetterBranding


def dao_get_letter_branding_or_platform_default(domain=None):
    letter_branding = None
    if domain:
        letter_branding = LetterBranding.query.filter(
            LetterBranding.domain == domain
        ).first()
    if not letter_branding:
        letter_branding = LetterBranding.query.filter(
            LetterBranding.platform_default == True  # noqa
        ).first()
    return letter_branding


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
