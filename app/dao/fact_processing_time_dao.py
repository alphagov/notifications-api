from sqlalchemy.dialects.postgresql import insert

from app import db
from app.dao.dao_utils import transactional
from app.models import FactProcessingTime


@transactional
def insert_update_processing_time(processing_time):
    '''
    This uses the Postgres upsert to avoid race conditions when two threads try and insert
    at the same row. The excluded object refers to values that we tried to insert but were
    rejected.
    http://docs.sqlalchemy.org/en/latest/dialects/postgresql.html#insert-on-conflict-upsert
    '''
    table = FactProcessingTime.__table__
    stmt = insert(table).values(
        bst_date=processing_time.bst_date,
        messages_total=processing_time.messages_total,
        messages_within_10_secs=processing_time.messages_within_10_secs
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.bst_date],
        set_={
            'messages_total': stmt.excluded.messages_total,
            'messages_within_10_secs': stmt.excluded.messages_within_10_secs
        }
    )
    db.session.connection().execute(stmt)
