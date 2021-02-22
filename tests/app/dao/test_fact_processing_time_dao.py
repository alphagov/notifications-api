from datetime import datetime

from app.dao import fact_processing_time_dao
from app.models import FactProcessingTime


def test_insert_update_processing_time(notify_db_session):
    data = FactProcessingTime(
        bst_date=datetime(2021, 2, 22).date(),
        messages_total=3,
        messages_within_10_secs=2
    )

    fact_processing_time_dao.insert_update_processing_time(data)

    result = FactProcessingTime.query.all()

    assert len(result) == 1
    assert result[0].bst_date == datetime(2021, 2, 22).date()
    assert result[0].messages_total == 3
    assert result[0].messages_within_10_secs == 2

    data = FactProcessingTime(
        bst_date=datetime(2021, 2, 22).date(),
        messages_total=4,
        messages_within_10_secs=3
    )

    fact_processing_time_dao.insert_update_processing_time(data)

    result = FactProcessingTime.query.all()

    assert len(result) == 1
    assert result[0].bst_date == datetime(2021, 2, 22).date()
    assert result[0].messages_total == 4
    assert result[0].messages_within_10_secs == 3
