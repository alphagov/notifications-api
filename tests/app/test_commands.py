from datetime import datetime

from app.commands import backfill_processing_time


def test_backfill_processing_time_works_for_correct_dates(mocker):
    send_mock = mocker.patch('app.commands.send_processing_time_for_start_and_end')

    backfill_processing_time.callback('2017-08-01', '2017-08-03')

    assert send_mock.call_count == 3
    send_mock.assert_any_call(datetime(2017, 7, 31, 23, 0), datetime(2017, 8, 1, 23, 0))
    send_mock.assert_any_call(datetime(2017, 8, 1, 23, 0), datetime(2017, 8, 2, 23, 0))
    send_mock.assert_any_call(datetime(2017, 8, 2, 23, 0), datetime(2017, 8, 3, 23, 0))
