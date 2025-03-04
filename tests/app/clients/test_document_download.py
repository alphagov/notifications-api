import pytest
import requests
import requests_mock

from app.clients.document_download import (
    DocumentDownloadClient,
    DocumentDownloadError,
)


@pytest.fixture(scope="function")
def document_download(client, mocker):
    current_app = mocker.Mock(
        config={
            "DOCUMENT_DOWNLOAD_API_HOST": "https://document-download",
            "DOCUMENT_DOWNLOAD_API_HOST_INTERNAL": "https://document-download-internal",
            "DOCUMENT_DOWNLOAD_API_KEY": "test-key",
        },
    )
    client = DocumentDownloadClient(current_app)
    return client


def test_get_upload_url(document_download):
    assert (
        document_download._get_upload_url("service-id")
        == "https://document-download-internal/services/service-id/documents"
    )


def test_get_upload_url_for_simulated_email(document_download):
    assert (
        document_download.get_upload_url_for_simulated_email("service-id")
        == "https://document-download/services/service-id/documents"
    )


def test_upload_document(document_download, mock_onwards_request_headers):
    with requests_mock.Mocker() as request_mock:
        request_mock.post(
            "https://document-download-internal/services/service-id/documents",
            json={"document": {"url": "https://document-download/services/service-id/documents/uploaded-url"}},
            request_headers={
                "Authorization": "Bearer test-key",
                "some-onwards": "request-headers",
            },
            status_code=201,
        )

        resp = document_download.upload_document("service-id", "abababab")

    assert resp == "https://document-download/services/service-id/documents/uploaded-url"


@pytest.mark.parametrize("confirmation_email", [None, "dev@test.notify"])
def test_upload_document_confirm_email(
    document_download,
    mock_onwards_request_headers,
    confirmation_email,
):
    with requests_mock.Mocker() as request_mock:
        request_mock.post(
            "https://document-download-internal/services/service-id/documents",
            json={"document": {"url": "https://document-download/services/service-id/documents/uploaded-url"}},
            request_headers={
                "Authorization": "Bearer test-key",
                "some-onwards": "request-headers",
            },
            status_code=201,
        )

        resp = document_download.upload_document("service-id", "abababab", confirmation_email=confirmation_email)

    assert resp == "https://document-download/services/service-id/documents/uploaded-url"

    request_json = request_mock.request_history[0].json()
    if confirmation_email:
        assert request_json["confirmation_email"] == confirmation_email

    else:
        assert "confirmation_email" not in request_json


@pytest.mark.parametrize("retention_period", [None, "1 week", "5 weeks"])
def test_upload_document_retention_period(
    document_download,
    mock_onwards_request_headers,
    retention_period,
):
    with requests_mock.Mocker() as request_mock:
        request_mock.post(
            "https://document-download-internal/services/service-id/documents",
            json={"document": {"url": "https://document-download/services/service-id/documents/uploaded-url"}},
            request_headers={
                "Authorization": "Bearer test-key",
                "some-onwards": "request-headers",
            },
            status_code=201,
        )

        resp = document_download.upload_document("service-id", "abababab", retention_period=retention_period)

    assert resp == "https://document-download/services/service-id/documents/uploaded-url"

    request_json = request_mock.request_history[0].json()
    if retention_period:
        assert request_json["retention_period"] == retention_period

    else:
        assert "retention_period" not in request_json


@pytest.mark.parametrize("status", [400, 413])
def test_should_raise_user_errors_as_DocumentDownloadErrors(document_download, mock_onwards_request_headers, status):
    with pytest.raises(DocumentDownloadError) as excinfo, requests_mock.Mocker() as request_mock:
        request_mock.post(
            "https://document-download-internal/services/service-id/documents",
            json={"error": "Invalid mime type"},
            status_code=status,
        )

        document_download.upload_document("service-id", "abababab")

    assert excinfo.value.message == "Invalid mime type"
    # 413 gets converted to 400 as well
    assert excinfo.value.status_code == 400


def test_should_raise_non_400_statuses_as_exceptions(document_download, mock_onwards_request_headers):
    with pytest.raises(Exception) as excinfo, requests_mock.Mocker() as request_mock:
        request_mock.post(
            "https://document-download-internal/services/service-id/documents",
            json={"error": "Auth Error Of Some Kind"},
            status_code=403,
        )

        document_download.upload_document("service-id", "abababab")

    assert type(excinfo.value) is Exception  # make sure it's a base exception, so will be handled as a 500 by v2 api
    assert str(excinfo.value) == 'Unhandled document download error: {"error": "Auth Error Of Some Kind"}'


def test_should_raise_exceptions_without_http_response_bodies_as_exceptions(
    document_download,
    mock_onwards_request_headers,
):
    with pytest.raises(Exception) as excinfo, requests_mock.Mocker() as request_mock:
        request_mock.post(
            "https://document-download-internal/services/service-id/documents", exc=requests.exceptions.ConnectTimeout
        )

        document_download.upload_document("service-id", "abababab")

    assert type(excinfo.value) is Exception  # make sure it's a base exception, so will be handled as a 500 by v2 api
    assert str(excinfo.value) == "Unhandled document download error: ConnectTimeout()"
