import json
import moto

from datetime import (
    datetime,
    timedelta
)

from flask import url_for, current_app
from app.models import (
    VerifyCode,
    User
)

from app import db, encryption

from tests import create_authorization_header
from freezegun import freeze_time

import app.celery.tasks


def test_user_verify_code_sms(notify_api,
                              sample_sms_code):
    """
    Tests POST endpoint '/<user_id>/verify/code'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_user_verify_code_sms_missing_code(notify_api,
                                           sample_sms_code):
    """
    Tests POST endpoint '/<user_id>/verify/code'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert not VerifyCode.query.first().code_used
            data = json.dumps({'code_type': sample_sms_code.code_type})
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            assert not VerifyCode.query.first().code_used


@moto.mock_sqs
def test_user_verify_code_email(notify_api,
                                sqs_client_conn,
                                sample_email_code):
    """
    Tests POST endpoint '/<user_id>/verify/code'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert not VerifyCode.query.first().code_used
            data = json.dumps({
                'code_type': sample_email_code.code_type,
                'code': sample_email_code.txt_code})
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204
            assert VerifyCode.query.first().code_used


def test_user_verify_code_email_bad_code(notify_api,
                                         sample_email_code):
    """
    Tests POST endpoint '/<user_id>/verify/code'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert not VerifyCode.query.first().code_used
            data = json.dumps({
                'code_type': sample_email_code.code_type,
                'code': "blah"})
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            assert not VerifyCode.query.first().code_used


def test_user_verify_code_email_expired_code(notify_api,
                                             sample_email_code):
    """
    Tests POST endpoint '/<user_id>/verify/code'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert not VerifyCode.query.first().code_used
            sample_email_code.expiry_datetime = (
                datetime.utcnow() - timedelta(hours=1))
            db.session.add(sample_email_code)
            db.session.commit()
            data = json.dumps({
                'code_type': sample_email_code.code_type,
                'code': sample_email_code.txt_code})
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            assert not VerifyCode.query.first().code_used


@freeze_time("2016-01-01 10:00:00.000000")
def test_user_verify_password(notify_api,
                              notify_db,
                              notify_db_session,
                              sample_user):
    """
    Tests POST endpoint '/<user_id>/verify/password'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'password': 'password'})
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204
            User.query.get(sample_user.id).logged_in_at == datetime.utcnow()


def test_user_verify_password_invalid_password(notify_api,
                                               sample_user):
    """
    Tests POST endpoint '/<user_id>/verify/password' invalid endpoint.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_user_verify_password_valid_password_resets_failed_logins(notify_api,
                                                                  sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_user_verify_password_missing_password(notify_api,
                                               sample_user):
    """
    Tests POST endpoint '/<user_id>/verify/password' missing password.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'bingo': 'bongo'})
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert 'Required field missing data' in json_resp['message']['password']


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_sms_code(notify_api,
                            sample_user,
                            sms_code_template,
                            mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code
    """

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({})
            auth_header = create_authorization_header()
            mocked = mocker.patch('app.user.rest.create_secret_code', return_value='11111')
            mocker.patch('app.celery.tasks.send_sms.apply_async')
            mocker.patch('uuid.uuid4', return_value='some_uuid')  # for the notification id
            resp = client.post(
                url_for('user.send_user_sms_code', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204
            assert mocked.call_count == 1
            encrypted = encryption.encrypt({
                'template': current_app.config['SMS_CODE_TEMPLATE_ID'],
                'template_version': 1,
                'to': sample_user.mobile_number,
                'personalisation': {
                    'verify_code': '11111'
                }
            })
            app.celery.tasks.send_sms.apply_async.assert_called_once_with(
                ([current_app.config['NOTIFY_SERVICE_ID'],
                  "some_uuid",
                  encrypted,
                  "2016-01-01T11:09:00.061258Z"]),
                queue="notify"
            )


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_code_for_sms_with_optional_to_field(notify_api,
                                                       sample_user,
                                                       sms_code_template,
                                                       mock_encryption,
                                                       mocker):
    """
    Tests POST endpoint '/<user_id>/code' successful sms with optional to field
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.user.rest.create_secret_code', return_value='11111')
            mocker.patch('uuid.uuid4', return_value='some_uuid')  # for the notification id
            mocker.patch('app.celery.tasks.send_sms.apply_async')
            data = json.dumps({'to': '+441119876757'})
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.send_user_sms_code', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 204
            encrypted = encryption.encrypt({
                'template': current_app.config['SMS_CODE_TEMPLATE_ID'],
                'template_version': 1,
                'to': '+441119876757',
                'personalisation': {
                    'verify_code': '11111'
                }
            })
            assert mocked.call_count == 1
            app.celery.tasks.send_sms.apply_async.assert_called_once_with(
                ([current_app.config['NOTIFY_SERVICE_ID'],
                  "some_uuid",
                  encrypted,
                  "2016-01-01T11:09:00.061258Z"]),
                queue="notify"
            )


def test_send_sms_code_returns_404_for_bad_input_data(notify_api, notify_db, notify_db_session):
    """
    Tests POST endpoint /user/<user_id>/sms-code return 404 for bad input data
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_email_verification(notify_api,
                                      sample_user,
                                      mocker,
                                      email_verification_template):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({})
            mocker.patch('uuid.uuid4', return_value='some_uuid')  # for the notification id
            mocked = mocker.patch('app.celery.tasks.send_email.apply_async')
            mocker.patch('notifications_utils.url_safe_token.generate_token', return_value='the-token')
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.send_user_email_verification', user_id=str(sample_user.id)),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204
            assert mocked.call_count == 1
            message = {
                'template': str(email_verification_template.id),
                'template_version': email_verification_template.version,
                'to': sample_user.email_address,
                'personalisation': {
                    'name': sample_user.name,
                    'url': current_app.config['ADMIN_BASE_URL'] + '/verify-email/' + 'the-token'
                }
            }
            app.celery.tasks.send_email.apply_async.assert_called_once_with(
                (str(current_app.config['NOTIFY_SERVICE_ID']),
                 'some_uuid',
                 encryption.encrypt(message),
                 "2016-01-01T11:09:00.061258Z"),
                queue="notify")


def test_send_email_verification_returns_404_for_bad_input_data(notify_api, notify_db, notify_db_session):
    """
    Tests POST endpoint /user/<user_id>/sms-code return 404 for bad input data
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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
