from datetime import datetime

from sqlalchemy import asc, or_

from app.models import LetterRate


def dao_get_current_letter_rates():
    return (
        LetterRate.query.filter(
            # We have rows for crown and non-crown but
            # - they should always be the same
            # - we don’t show them separately anywhere
            #
            # So let’s just ignore non-crown for now
            LetterRate.crown.is_(True),
            LetterRate.start_date <= datetime.utcnow(),
            or_(
                LetterRate.end_date.is_(None),
                LetterRate.end_date > datetime.utcnow(),
            ),
        )
        .order_by(
            asc(LetterRate.sheet_count),
            asc(LetterRate.rate),
            asc(LetterRate.post_class),
        )
        .all()
    )
