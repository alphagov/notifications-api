import pytest
import requests
import requests_mock

from app.clients.document_download import (
    DocumentDownloadClient,
    DocumentDownloadError,
)


@pytest.fixture(scope='function')
def document_download(client, mocker):
    client = DocumentDownloadClient()
    current_app = mocker.Mock(config={
        'DOCUMENT_DOWNLOAD_API_HOST': 'https://document-download',
        'DOCUMENT_DOWNLOAD_API_KEY': 'test-key'
    })
    client.init_app(current_app)
    return client


def test_get_upload_url(document_download):
    assert document_download.get_upload_url('service-id') == 'https://document-download/services/service-id/documents'


def test_upload_document(document_download):
    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://document-download/services/service-id/documents', json={
            'document': {'url': 'https://document-download/services/service-id/documents/uploaded-url'}
        }, request_headers={
            'Authorization': 'Bearer test-key',
        }, status_code=201)

        resp = document_download.upload_document('service-id', 'abababab')

    assert resp == 'https://document-download/services/service-id/documents/uploaded-url'


def test_should_raise_400s_as_DocumentDownloadErrors(document_download):
    with pytest.raises(DocumentDownloadError) as excinfo, requests_mock.Mocker() as request_mock:
        request_mock.post('https://document-download/services/service-id/documents', json={
            'error': 'Invalid mime type'
        }, status_code=400)

        document_download.upload_document('service-id', 'abababab')

    assert excinfo.value.message == 'Invalid mime type'
    assert excinfo.value.status_code == 400


def test_should_raise_non_400_statuses_as_exceptions(document_download):
    with pytest.raises(Exception) as excinfo, requests_mock.Mocker() as request_mock:
        request_mock.post(
            'https://document-download/services/service-id/documents',
            json={'error': 'Auth Error Of Some Kind'},
            status_code=403
        )

        document_download.upload_document('service-id', 'abababab')

    assert type(excinfo.value) == Exception  # make sure it's a base exception, so will be handled as a 500 by v2 api
    assert str(excinfo.value) == 'Unhandled document download error: {"error": "Auth Error Of Some Kind"}'


def test_should_raise_exceptions_without_http_response_bodies_as_exceptions(document_download):
    with pytest.raises(Exception) as excinfo, requests_mock.Mocker() as request_mock:
        request_mock.post(
            'https://document-download/services/service-id/documents',
            exc=requests.exceptions.ConnectTimeout
        )

        document_download.upload_document('service-id', 'abababab')

    assert type(excinfo.value) == Exception  # make sure it's a base exception, so will be handled as a 500 by v2 api
    assert str(excinfo.value) == 'Unhandled document download error: ConnectTimeout()'
