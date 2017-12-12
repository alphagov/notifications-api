from app import db
from app.dao.dao_utils import transactional
from app.models import LetterRate


@transactional
def dao_create_letter_rate(letter_rate):
    db.session.add(letter_rate)


def get_letter_rates_for_daterange(date, crown, sheet_count, post_class='second'):
    rates = LetterRate.query.filter(
        LetterRate.start_date <= date
    ).filter((LetterRate.end_date == None) |  # noqa
             (LetterRate.end_date > date)
             ).filter(
        LetterRate.crown == crown
    ).filter(
        LetterRate.sheet_count == sheet_count
    ).filter(
        LetterRate.post_class == post_class
    ).all()
    return rates
