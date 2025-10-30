import json
from dataclasses import asdict
from datetime import date

from flask import url_for
from freezegun import freeze_time

from tests import create_admin_authorization_header
from tests.app.db import (
    create_complaint,
    create_notification,
    create_service,
    create_template,
)


def test_get_all_complaints_returns_complaints_for_multiple_services(client, notify_db_session):
    service = create_service(service_name="service1")
    template = create_template(service=service)
    notification = create_notification(template=template)
    complaint_1 = create_complaint()  # default service
    complaint_2 = create_complaint(service=service, notification=notification)

    response = client.get("/complaint", headers=[create_admin_authorization_header()])
    complaints = json.loads(response.get_data(as_text=True))["complaints"]

    assert response.status_code == 200
    assert complaints == [
        asdict(complaint_2.serialize()),
        asdict(complaint_1.serialize()),
    ]


def test_get_all_complaints_returns_empty_complaints_list(client):
    response = client.get("/complaint", headers=[create_admin_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["complaints"] == []


def test_get_all_complaints_returns_pagination_links(mocker, client, notify_db_session):
    mocker.patch.dict("app.dao.complaint_dao.current_app.config", {"PAGE_SIZE": 1})
    service_1 = create_service(service_name="service1")
    service_2 = create_service(service_name="service2")

    create_complaint()
    create_complaint(service=service_1)
    create_complaint(service=service_2)

    response = client.get(
        url_for("complaint.get_all_complaints", page=2), headers=[create_admin_authorization_header()]
    )

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["links"] == {
        "last": "/complaint?page=3",
        "next": "/complaint?page=3",
        "prev": "/complaint?page=1",
    }


def test_get_complaint_with_start_and_end_date_passes_these_to_dao_function(mocker, client):
    start_date = date(2018, 6, 11)
    end_date = date(2018, 6, 11)
    dao_mock = mocker.patch("app.complaint.complaint_rest.fetch_count_of_complaints", return_value=3)
    response = client.get(
        url_for("complaint.get_complaint_count", start_date=start_date, end_date=end_date),
        headers=[create_admin_authorization_header()],
    )

    dao_mock.assert_called_once_with(start_date=start_date, end_date=end_date)
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == 3


@freeze_time("2018-06-01 11:00:00")
def test_get_complaint_sets_start_and_end_date_to_today_if_not_specified(mocker, client):
    dao_mock = mocker.patch("app.complaint.complaint_rest.fetch_count_of_complaints", return_value=5)
    response = client.get(url_for("complaint.get_complaint_count"), headers=[create_admin_authorization_header()])

    dao_mock.assert_called_once_with(start_date=date.today(), end_date=date.today())
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == 5


def test_get_complaint_with_invalid_data_returns_400_status_code(client):
    start_date = "1234-56-78"
    response = client.get(
        url_for("complaint.get_complaint_count", start_date=start_date), headers=[create_admin_authorization_header()]
    )

    assert response.status_code == 400
    assert response.json["errors"][0]["message"] == "start_date month must be in 1..12"
