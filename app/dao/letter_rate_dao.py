from datetime import UTC, datetime

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
            LetterRate.start_date <= datetime.now(UTC).replace(tzinfo=None),
            or_(
                LetterRate.end_date.is_(None),
                LetterRate.end_date > datetime.now(UTC).replace(tzinfo=None),
            ),
        )
        .order_by(
            asc(LetterRate.sheet_count),
            asc(LetterRate.rate),
            asc(LetterRate.post_class),
        )
        .all()
    )
