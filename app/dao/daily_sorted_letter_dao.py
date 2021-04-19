from datetime import datetime

from sqlalchemy.dialects.postgresql import insert

from app import db
from app.dao.dao_utils import autocommit
from app.models import DailySortedLetter


def dao_get_daily_sorted_letter_by_billing_day(billing_day):
    return DailySortedLetter.query.filter_by(
        billing_day=billing_day
    ).first()


@autocommit
def dao_create_or_update_daily_sorted_letter(new_daily_sorted_letter):
    '''
    This uses the Postgres upsert to avoid race conditions when two threads try and insert
    at the same row. The excluded object refers to values that we tried to insert but were
    rejected.
    http://docs.sqlalchemy.org/en/latest/dialects/postgresql.html#insert-on-conflict-upsert
    '''
    table = DailySortedLetter.__table__
    stmt = insert(table).values(
        billing_day=new_daily_sorted_letter.billing_day,
        file_name=new_daily_sorted_letter.file_name,
        unsorted_count=new_daily_sorted_letter.unsorted_count,
        sorted_count=new_daily_sorted_letter.sorted_count)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.billing_day, table.c.file_name],
        set_={
            'unsorted_count': stmt.excluded.unsorted_count,
            'sorted_count': stmt.excluded.sorted_count,
            'updated_at': datetime.utcnow()
        }
    )
    db.session.connection().execute(stmt)
