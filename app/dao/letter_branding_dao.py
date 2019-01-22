from app.models import LetterBranding


def get_letter_branding_or_platform_default(domain=None):
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


def get_all_letter_branding():
    return LetterBranding.query.order_by(LetterBranding.name).all()
