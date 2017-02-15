import json
import pytest

from datetime import (
    datetime,
    timedelta
)

from flask import url_for, current_app
from app.dao.services_dao import dao_update_service, dao_fetch_service_by_id
from app.models import (
    VerifyCode,
    User,
    Notification
)

from app import db

from tests import create_authorization_header
from freezegun import freeze_time

import app.celery.tasks


def test_user_verify_code(client,
                          sample_sms_code):
    assert not VerifyCode.query.first().code_used
    data = json.dumps({
        'code_type': sample_sms_code.code_type,
        'code': sample_sms_code.txt_code})
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 204
    assert VerifyCode.query.first().code_used


def test_user_verify_code_missing_code(client,
                                       sample_sms_code):
    assert not VerifyCode.query.first().code_used
    data = json.dumps({'code_type': sample_sms_code.code_type})
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 400
    assert not VerifyCode.query.first().code_used
    assert User.query.get(sample_sms_code.user.id).failed_login_count == 0


def test_user_verify_code_bad_code_and_increments_failed_login_count(client,
                                                                     sample_sms_code):
    assert not VerifyCode.query.first().code_used
    data = json.dumps({
        'code_type': sample_sms_code.code_type,
        'code': "blah"})
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 404
    assert not VerifyCode.query.first().code_used
    assert User.query.get(sample_sms_code.user.id).failed_login_count == 1


def test_user_verify_code_expired_code_and_increments_failed_login_count(
        client,
        sample_sms_code):
    assert not VerifyCode.query.first().code_used
    sample_sms_code.expiry_datetime = (
        datetime.utcnow() - timedelta(hours=1))
    db.session.add(sample_sms_code)
    db.session.commit()
    data = json.dumps({
        'code_type': sample_sms_code.code_type,
        'code': sample_sms_code.txt_code})
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 400
    assert not VerifyCode.query.first().code_used
    assert User.query.get(sample_sms_code.user.id).failed_login_count == 1


@freeze_time("2016-01-01 10:00:00.000000")
def test_user_verify_password(client,
                              notify_db_session,
                              sample_user):
    data = json.dumps({'password': 'password'})
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 204
    assert User.query.get(sample_user.id).logged_in_at == datetime.utcnow()


def test_user_verify_password_invalid_password(client,
                                               sample_user):
    data = json.dumps({'password': 'bad password'})
    auth_header = create_authorization_header()

    assert sample_user.failed_login_count == 0

    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert 'Incorrect password' in json_resp['message']['password']
    assert sample_user.failed_login_count == 1


def test_user_verify_password_valid_password_resets_failed_logins(client,
                                                                  sample_user):
    data = json.dumps({'password': 'bad password'})
    auth_header = create_authorization_header()

    assert sample_user.failed_login_count == 0

    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert 'Incorrect password' in json_resp['message']['password']

    assert sample_user.failed_login_count == 1

    data = json.dumps({'password': 'password'})
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 204
    assert sample_user.failed_login_count == 0


def test_user_verify_password_missing_password(client,
                                               sample_user):
    data = json.dumps({'bingo': 'bongo'})
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert 'Required field missing data' in json_resp['message']['password']


@pytest.mark.parametrize('research_mode', [True, False])
@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_sms_code(notify_api,
                            sample_user,
                            sms_code_template,
                            mocker,
                            research_mode):
    """
    Tests POST endpoint /user/<user_id>/sms-code
    """

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            if research_mode:
                notify_service = dao_fetch_service_by_id(current_app.config['NOTIFY_SERVICE_ID'])
                notify_service.research_mode = True
                dao_update_service(notify_service)

            data = json.dumps({})
            auth_header = create_authorization_header()
            mocked = mocker.patch('app.user.rest.create_secret_code', return_value='11111')
            mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

            resp = client.post(
                url_for('user.send_user_sms_code', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204

            assert mocked.call_count == 1
            assert VerifyCode.query.count() == 1
            assert VerifyCode.query.first().check_code('11111')

            assert Notification.query.count() == 1
            notification = Notification.query.first()
            assert notification.personalisation == {'verify_code': '11111'}
            assert notification.to == sample_user.mobile_number
            assert str(notification.service_id) == current_app.config['NOTIFY_SERVICE_ID']

            app.celery.provider_tasks.deliver_sms.apply_async.assert_called_once_with(
                ([str(notification.id)]),
                queue="notify"
            )


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_code_for_sms_with_optional_to_field(notify_api,
                                                       sample_user,
                                                       sms_code_template,
                                                       mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code with optional to field
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            to_number = '+441119876757'
            mocked = mocker.patch('app.user.rest.create_secret_code', return_value='11111')
            mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
            data = json.dumps({'to': to_number})
            auth_header = create_authorization_header()

            resp = client.post(
                url_for('user.send_user_sms_code', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 204
            assert mocked.call_count == 1
            notification = Notification.query.first()
            assert notification.to == to_number
            app.celery.provider_tasks.deliver_sms.apply_async.assert_called_once_with(
                ([str(notification.id)]),
                queue="notify"
            )


def test_send_sms_code_returns_404_for_bad_input_data(client):
    data = json.dumps({})
    import uuid
    uuid_ = uuid.uuid4()
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.send_user_sms_code', user_id=uuid_),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))['message'] == 'No result found'


def test_send_user_email_verification(client,
                                      sample_user,
                                      mocker,
                                      email_verification_template):
    data = json.dumps({})
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.send_user_email_verification', user_id=str(sample_user.id)),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 204
    notification = Notification.query.first()
    mocked.assert_called_once_with(([str(notification.id)]), queue="notify")


def test_send_email_verification_returns_404_for_bad_input_data(client, notify_db, notify_db_session, mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code return 404 for bad input data
    """
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = json.dumps({})
    import uuid
    uuid_ = uuid.uuid4()
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.send_user_email_verification', user_id=uuid_),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))['message'] == 'No result found'
    assert mocked.call_count == 0
