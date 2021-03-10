from datetime import datetime

from freezegun import freeze_time

from app.dao import fact_processing_time_dao
from app.dao.fact_processing_time_dao import (
    get_processing_time_percentage_for_date_range,
)
from app.models import FactProcessingTime
from tests.app.db import create_process_time


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
    assert result[0].created_at
    assert not result[0].updated_at

    data = FactProcessingTime(
        bst_date=datetime(2021, 2, 22).date(),
        messages_total=4,
        messages_within_10_secs=3
    )
    with freeze_time("2021-02-23 13:23:33"):
        fact_processing_time_dao.insert_update_processing_time(data)

    result = FactProcessingTime.query.all()

    assert len(result) == 1
    assert result[0].bst_date == datetime(2021, 2, 22).date()
    assert result[0].messages_total == 4
    assert result[0].messages_within_10_secs == 3
    assert result[0].created_at
    assert result[0].updated_at == datetime(2021, 2, 23, 13, 23, 33)


def test_get_processing_time_percentage_for_date_range(notify_db_session):
    create_process_time(
        bst_date='2021-02-21',
        messages_total=5,
        messages_within_10_secs=4
    )
    create_process_time(
        bst_date='2021-02-22',
        messages_total=3,
        messages_within_10_secs=2
    )
    create_process_time(
        bst_date='2021-02-23',
        messages_total=4,
        messages_within_10_secs=3
    )

    results = get_processing_time_percentage_for_date_range('2021-02-22', '2021-02-22')

    assert len(results) == 1
    assert results[0].date == '2021-02-22'
    assert results[0].messages_total == 3
    assert results[0].messages_within_10_secs == 2
    assert round(results[0].percentage, 1) == 66.7
