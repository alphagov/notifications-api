import pytest

from app.models import Notification, INVITE_PENDING

from tests.app.db import create_invited_org_user


@pytest.mark.parametrize('platform_admin, expected_invited_by', (
    (True, 'The GOV.UK Notify team'),
    (False, 'Test User')
))
@pytest.mark.parametrize('extra_args, expected_start_of_invite_url', [
    (
        {},
        'http://localhost:6012/organisation-invitation/'
    ),
    (
        {'invite_link_host': 'https://www.example.com'},
        'https://www.example.com/organisation-invitation/'
    ),
])
def test_create_invited_org_user(
    admin_request,
    sample_organisation,
    sample_user,
    mocker,
    org_invite_email_template,
    extra_args,
    expected_start_of_invite_url,
    platform_admin,
    expected_invited_by,
):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    email_address = 'invited_user@example.com'
    sample_user.platform_admin = platform_admin

    data = dict(
        organisation=str(sample_organisation.id),
        email_address=email_address,
        invited_by=str(sample_user.id),
        **extra_args
    )

    json_resp = admin_request.post(
        'organisation_invite.invite_user_to_org',
        organisation_id=sample_organisation.id,
        _data=data,
        _expected_status=201
    )

    assert json_resp['data']['organisation'] == str(sample_organisation.id)
    assert json_resp['data']['email_address'] == email_address
    assert json_resp['data']['invited_by'] == str(sample_user.id)
    assert json_resp['data']['status'] == INVITE_PENDING
    assert json_resp['data']['id']

    notification = Notification.query.first()

    assert notification.reply_to_text == sample_user.email_address

    assert len(notification.personalisation.keys()) == 3
    assert notification.personalisation['organisation_name'] == 'sample organisation'
    assert notification.personalisation['user_name'] == expected_invited_by
    assert notification.personalisation['url'].startswith(expected_start_of_invite_url)
    assert len(notification.personalisation['url']) > len(expected_start_of_invite_url)

    mocked.assert_called_once_with([(str(notification.id))], queue="notify-internal-tasks")


def test_create_invited_user_invalid_email(admin_request, sample_organisation, sample_user, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    email_address = 'notanemail'

    data = {
        'service': str(sample_organisation.id),
        'email_address': email_address,
        'invited_by': str(sample_user.id),
    }

    json_resp = admin_request.post(
        'organisation_invite.invite_user_to_org',
        organisation_id=sample_organisation.id,
        _data=data,
        _expected_status=400
    )

    assert json_resp['errors'][0]['message'] == 'email_address Not a valid email address'
    assert mocked.call_count == 0


def test_get_all_invited_users_by_service(admin_request, sample_organisation, sample_user):
    for i in range(5):
        create_invited_org_user(
            sample_organisation,
            sample_user,
            email_address='invited_user_{}@service.gov.uk'.format(i)
        )

    json_resp = admin_request.get(
        'organisation_invite.get_invited_org_users_by_organisation',
        organisation_id=sample_organisation.id
    )

    assert len(json_resp['data']) == 5
    for invite in json_resp['data']:
        assert invite['organisation'] == str(sample_organisation.id)
        assert invite['invited_by'] == str(sample_user.id)
        assert invite['id']


def test_get_invited_users_by_service_with_no_invites(admin_request, sample_organisation):
    json_resp = admin_request.get(
        'organisation_invite.get_invited_org_users_by_organisation',
        organisation_id=sample_organisation.id
    )
    assert len(json_resp['data']) == 0


def test_get_invited_user_by_organisation(admin_request, sample_invited_org_user):
    json_resp = admin_request.get(
        'organisation_invite.get_invited_org_user_by_organisation',
        organisation_id=sample_invited_org_user.organisation.id,
        invited_org_user_id=sample_invited_org_user.id
    )
    assert json_resp['data']['email_address'] == sample_invited_org_user.email_address


def test_get_invited_user_by_organisation_when_user_does_not_belong_to_the_org(
    admin_request,
    sample_invited_org_user,
    fake_uuid,
):
    json_resp = admin_request.get(
        'organisation_invite.get_invited_org_user_by_organisation',
        organisation_id=fake_uuid,
        invited_org_user_id=sample_invited_org_user.id,
        _expected_status=404
    )
    assert json_resp['result'] == 'error'


def test_update_org_invited_user_set_status_to_cancelled(admin_request, sample_invited_org_user):
    data = {'status': 'cancelled'}

    json_resp = admin_request.post(
        'organisation_invite.update_org_invite_status',
        organisation_id=sample_invited_org_user.organisation_id,
        invited_org_user_id=sample_invited_org_user.id,
        _data=data
    )
    assert json_resp['data']['status'] == 'cancelled'


def test_update_org_invited_user_for_wrong_service_returns_404(admin_request, sample_invited_org_user, fake_uuid):
    data = {'status': 'cancelled'}

    json_resp = admin_request.post(
        'organisation_invite.update_org_invite_status',
        organisation_id=fake_uuid,
        invited_org_user_id=sample_invited_org_user.id,
        _data=data,
        _expected_status=404
    )
    assert json_resp['message'] == 'No result found'


def test_update_org_invited_user_for_invalid_data_returns_400(admin_request, sample_invited_org_user):
    data = {'status': 'garbage'}

    json_resp = admin_request.post(
        'organisation_invite.update_org_invite_status',
        organisation_id=sample_invited_org_user.organisation_id,
        invited_org_user_id=sample_invited_org_user.id,
        _data=data,
        _expected_status=400
    )
    assert len(json_resp['errors']) == 1
    assert json_resp['errors'][0]['message'] == 'status garbage is not one of [pending, accepted, cancelled]'
