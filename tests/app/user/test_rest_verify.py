import json
import moto
from datetime import (datetime, timedelta)
from flask import url_for

from app.models import (VerifyCode)

import app.celery.tasks
from app import db, encryption
from tests import create_authorization_header


def test_user_verify_code_sms(notify_api,
                              notify_db,
                              notify_db_session,
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
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204
            assert VerifyCode.query.first().code_used


def test_user_verify_code_sms_missing_code(notify_api,
                                           notify_db,
                                           notify_db_session,
                                           sample_sms_code):
    """
    Tests POST endpoint '/<user_id>/verify/code'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert not VerifyCode.query.first().code_used
            data = json.dumps({'code_type': sample_sms_code.code_type})
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            assert not VerifyCode.query.first().code_used


@moto.mock_sqs
def test_user_verify_code_email(notify_api,
                                notify_db,
                                notify_db_session,
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
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204
            assert VerifyCode.query.first().code_used


def test_user_verify_code_email_bad_code(notify_api,
                                         notify_db,
                                         notify_db_session,
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
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            assert not VerifyCode.query.first().code_used


def test_user_verify_code_email_expired_code(notify_api,
                                             notify_db,
                                             notify_db_session,
                                             sample_email_code):
    """
    Tests POST endpoint '/<user_id>/verify/code'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert not VerifyCode.query.first().code_used
            sample_email_code.expiry_datetime = (
                datetime.now() - timedelta(hours=1))
            db.session.add(sample_email_code)
            db.session.commit()
            data = json.dumps({
                'code_type': sample_email_code.code_type,
                'code': sample_email_code.txt_code})
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_email_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            assert not VerifyCode.query.first().code_used


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
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_password', user_id=sample_user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204


def test_user_verify_password_invalid_password(notify_api,
                                               notify_db,
                                               notify_db_session,
                                               sample_user):
    """
    Tests POST endpoint '/<user_id>/verify/password' invalid endpoint.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'password': 'bad password'})
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_password', user_id=sample_user.id),
                method='POST',
                request_body=data)

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
                                                                  notify_db,
                                                                  notify_db_session,
                                                                  sample_user):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'password': 'bad password'})
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_password', user_id=sample_user.id),
                method='POST',
                request_body=data)

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
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_password', user_id=sample_user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 204
            assert sample_user.failed_login_count == 0


def test_user_verify_password_missing_password(notify_api,
                                               notify_db,
                                               notify_db_session,
                                               sample_user):
    """
    Tests POST endpoint '/<user_id>/verify/password' missing password.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'bingo': 'bongo'})
            auth_header = create_authorization_header(
                path=url_for('user.verify_user_password', user_id=sample_user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert 'Required field missing data' in json_resp['message']['password']


def test_send_user_code_for_sms(notify_api,
                                sample_sms_code,
                                mock_secret_code,
                                mock_celery_send_sms_code):
    """
   Tests POST endpoint '/<user_id>/code' successful sms
   """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'code_type': 'sms'})
            auth_header = create_authorization_header(
                path=url_for('user.send_user_code', user_id=sample_sms_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.send_user_code', user_id=sample_sms_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 204
            encrpyted = encryption.encrypt({'to': sample_sms_code.user.mobile_number, 'secret_code': '11111'})
            app.celery.tasks.send_sms_code.apply_async.assert_called_once_with([encrpyted], queue='sms_code')


def test_send_user_code_for_sms_with_optional_to_field(notify_api,
                                                       sample_sms_code,
                                                       mock_secret_code,
                                                       mock_celery_send_sms_code):
    """
   Tests POST endpoint '/<user_id>/code' successful sms with optional to field
   """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            data = json.dumps({'code_type': 'sms', 'to': '+441119876757'})
            auth_header = create_authorization_header(
                path=url_for('user.send_user_code', user_id=sample_sms_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.send_user_code', user_id=sample_sms_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 204
            encrypted = encryption.encrypt({'to': '+441119876757', 'secret_code': '11111'})
            app.celery.tasks.send_sms_code.apply_async.assert_called_once_with([encrypted], queue='sms_code')


def test_send_user_code_for_email(notify_api,
                                  sample_email_code,
                                  mock_secret_code,
                                  mock_celery_send_email_code,
                                  mock_encryption):
    """
   Tests POST endpoint '/<user_id>/code' successful email
   """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'code_type': 'email'})
            auth_header = create_authorization_header(
                path=url_for('user.send_user_code', user_id=sample_email_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.send_user_code', user_id=sample_email_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204

            app.celery.tasks.send_email_code.apply_async.assert_called_once_with(['something_encrypted'],
                                                                                 queue='email_code')


def test_send_user_code_for_email_uses_optional_to_field(notify_api,
                                                         sample_email_code,
                                                         mock_secret_code,
                                                         mock_celery_send_email_code,
                                                         mock_encryption):
    """
   Tests POST endpoint '/<user_id>/code' successful email with included in body
   """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'code_type': 'email', 'to': 'different@email.gov.uk'})
            auth_header = create_authorization_header(
                path=url_for('user.send_user_code', user_id=sample_email_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.send_user_code', user_id=sample_email_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204

            app.celery.tasks.send_email_code.apply_async.assert_called_once_with(['something_encrypted'],
                                                                                 queue='email_code')


def test_request_verify_code_schema_invalid_code_type(notify_api, notify_db, notify_db_session, sample_user):
    from app.schemas import request_verify_code_schema
    data = json.dumps({'code_type': 'not_sms'})
    code, error = request_verify_code_schema.loads(data)
    assert error == {'code_type': ['Invalid code type']}


def test_request_verify_code_schema_with_to(notify_api, notify_db, notify_db_session, sample_user):
    from app.schemas import request_verify_code_schema
    data = json.dumps({'code_type': 'sms', 'to': 'some@one.gov.uk'})
    code, error = request_verify_code_schema.loads(data)
    assert code == {'code_type': 'sms', 'to': 'some@one.gov.uk'}
    assert error == {}
