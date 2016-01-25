import json
from datetime import (datetime, timedelta)
from flask import url_for
from app.models import (User, Service, VerifyCode)
from app import db
from tests import create_authorization_header


def test_user_verify_code_sms(notify_api,
                              notify_db,
                              notify_db_session,
                              sample_admin_service_id,
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
                service_id=sample_admin_service_id,
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
                                           sample_admin_service_id,
                                           sample_sms_code):
    """
    Tests POST endpoint '/<user_id>/verify/code'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert not VerifyCode.query.first().code_used
            data = json.dumps({'code_type': sample_sms_code.code_type})
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
                path=url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            assert not VerifyCode.query.first().code_used


def test_user_verify_code_email(notify_api,
                                notify_db,
                                notify_db_session,
                                sample_admin_service_id,
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
                service_id=sample_admin_service_id,
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
                                         sample_admin_service_id,
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
                service_id=sample_admin_service_id,
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
                                             sample_admin_service_id,
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
                service_id=sample_admin_service_id,
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
                              sample_user,
                              sample_admin_service_id):
    """
    Tests POST endpoint '/<user_id>/verify/password'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'password': 'password'})
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
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
                                               sample_user,
                                               sample_admin_service_id):
    """
    Tests POST endpoint '/<user_id>/verify/password' invalid endpoint.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'password': 'bad password'})
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
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


def test_user_verify_password_missing_password(notify_api,
                                               notify_db,
                                               notify_db_session,
                                               sample_user,
                                               sample_admin_service_id):
    """
    Tests POST endpoint '/<user_id>/verify/password' missing password.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'bingo': 'bongo'})
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
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
