import pytest

from app.models import EmailBranding


def test_get_email_branding_options(admin_request, notify_db, notify_db_session):
    email_branding1 = EmailBranding(colour='#FFFFFF', logo='/path/image.png', name='Org1')
    email_branding2 = EmailBranding(colour='#000000', logo='/path/other.png', name='Org2')
    notify_db.session.add_all([email_branding1, email_branding2])
    notify_db.session.commit()

    email_branding = admin_request.get(
        'email_branding.get_email_branding_options'
    )['email_branding']

    assert len(email_branding) == 2
    assert {
        email_branding['id'] for email_branding in email_branding
    } == {
        str(email_branding1.id), str(email_branding2.id)
    }


def test_get_email_branding_by_id(admin_request, notify_db, notify_db_session):
    email_branding = EmailBranding(colour='#FFFFFF', logo='/path/image.png', name='Some Org', text='My Org')
    notify_db.session.add(email_branding)
    notify_db.session.commit()

    response = admin_request.get(
        'email_branding.get_email_branding_by_id',
        _expected_status=200,
        email_branding_id=email_branding.id
    )

    assert set(response['email_branding'].keys()) == {'colour', 'logo', 'name', 'id', 'text',
                                                      'banner_colour', 'single_id_colour', 'domain'}
    assert response['email_branding']['colour'] == '#FFFFFF'
    assert response['email_branding']['logo'] == '/path/image.png'
    assert response['email_branding']['name'] == 'Some Org'
    assert response['email_branding']['text'] == 'My Org'
    assert response['email_branding']['id'] == str(email_branding.id)


def test_post_create_email_branding(admin_request, notify_db_session):
    data = {
        'name': 'test email_branding',
        'colour': '#0000ff',
        'banner_colour': '#808080',
        'single_id_colour': '#FF0000',
        'logo': '/images/test_x2.png',
        'domain': 'gov.uk'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )
    assert data['name'] == response['data']['name']
    assert data['colour'] == response['data']['colour']
    assert data['banner_colour'] == response['data']['banner_colour']
    assert data['single_id_colour'] == response['data']['single_id_colour']
    assert data['logo'] == response['data']['logo']
    assert data['name'] == response['data']['text']
    assert data['domain'] == response['data']['domain']


def test_post_create_email_branding_without_logo_is_ok(admin_request, notify_db_session):
    data = {
        'name': 'test email_branding',
        'colour': '#0000ff',
    }
    admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201,
    )


def test_post_create_email_branding_without_name_or_colour_is_valid(admin_request, notify_db_session):
    data = {
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )

    assert response['data']['logo'] == data['logo']
    assert response['data']['name'] is None
    assert response['data']['colour'] is None
    assert response['data']['text'] is None


def test_post_create_email_branding_with_text(admin_request, notify_db_session):
    data = {
        'text': 'text for brand',
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )

    assert response['data']['logo'] == data['logo']
    assert response['data']['name'] is None
    assert response['data']['colour'] is None
    assert response['data']['text'] == 'text for brand'


def test_post_create_email_branding_with_text_and_name(admin_request, notify_db_session):
    data = {
        'name': 'name for brand',
        'text': 'text for brand',
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )

    assert response['data']['logo'] == data['logo']
    assert response['data']['name'] == 'name for brand'
    assert response['data']['colour'] is None
    assert response['data']['text'] == 'text for brand'


def test_post_create_email_branding_with_text_as_none_and_name(admin_request, notify_db_session):
    data = {
        'name': 'name for brand',
        'text': None,
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )

    assert response['data']['logo'] == data['logo']
    assert response['data']['name'] == 'name for brand'
    assert response['data']['colour'] is None
    assert response['data']['text'] is None


@pytest.mark.parametrize('data_update', [
    ({'name': 'test email_branding 1'}),
    ({'logo': 'images/text_x3.png', 'colour': '#ffffff'}),
    ({'logo': 'images/text_x3.png', 'banner_colour': '#ffffff', 'single_id_colour': '#808080'}),
    ({'logo': 'images/text_x3.png', 'banner_colour': '#ffffff', 'single_id_colour': '#808080', 'domain': 'gov.uk'}),
])
def test_post_update_email_branding_updates_field(admin_request, notify_db_session, data_update):
    data = {
        'name': 'test email_branding',
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )

    email_branding_id = response['data']['id']

    response = admin_request.post(
        'email_branding.update_email_branding',
        _data=data_update,
        email_branding_id=email_branding_id
    )

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert str(email_branding[0].id) == email_branding_id
    for key in data_update.keys():
        assert getattr(email_branding[0], key) == data_update[key]
    assert email_branding[0].text == email_branding[0].name


@pytest.mark.parametrize('data_update', [
    ({'text': 'text email branding'}),
    ({'text': 'new text', 'name': 'new name'}),
    ({'text': None, 'name': 'test name'}),
])
def test_post_update_email_branding_updates_field_with_text(admin_request, notify_db_session, data_update):
    data = {
        'name': 'test email_branding',
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )

    email_branding_id = response['data']['id']

    response = admin_request.post(
        'email_branding.update_email_branding',
        _data=data_update,
        email_branding_id=email_branding_id
    )

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert str(email_branding[0].id) == email_branding_id
    for key in data_update.keys():
        assert getattr(email_branding[0], key) == data_update[key]
